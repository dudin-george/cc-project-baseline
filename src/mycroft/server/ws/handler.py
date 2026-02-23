"""WebSocket endpoint: auth flow, message routing, agent dispatch."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from mycroft.shared.protocol import (
    AuthResult,
    ConfirmResponse,
    ErrorMessage,
    PingMessage,
    StateSyncMessage,
    StepTransition,
    StepId,
    StepState as ProtoStepState,
    TurnComplete,
    parse_client_message,
)
from mycroft.server.auth import validate_api_key
from mycroft.server.ws.connection_manager import manager
from mycroft.server.state.project import ProjectState
from mycroft.server.state import conversation as conv
from mycroft.server.pipeline import state as pipeline
from mycroft.server.pipeline.state import PipelineError
from mycroft.server.agents.registry import get_agent

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds


async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    project_id: str | None = None

    try:
        # --- Auth phase ---
        raw = await asyncio.wait_for(ws.receive_json(), timeout=30)
        msg = parse_client_message(raw)

        if msg.type != "auth":
            await ws.send_json(
                AuthResult(success=False, error="First message must be auth").model_dump()
            )
            await ws.close(code=4000)
            return

        if not validate_api_key(msg.api_key):
            await ws.send_json(
                AuthResult(success=False, error="Invalid API key").model_dump()
            )
            await ws.close(code=4003)
            return

        # Load or create project
        if msg.project_id and ProjectState.exists(msg.project_id):
            project = ProjectState.load(msg.project_id)
        else:
            project = ProjectState()
            project.save()

        project_id = project.project_id
        await manager.connect(project_id, ws)

        # Send auth result + state sync
        await ws.send_json(
            AuthResult(success=True, project_id=project_id).model_dump()
        )
        await _send_state_sync(ws, project)

        logger.info("Client authenticated for project %s", project_id)

        # --- Message loop with heartbeat ---
        async def _heartbeat() -> None:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                try:
                    await ws.send_json(PingMessage().model_dump())
                except Exception:
                    break

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            while True:
                raw = await ws.receive_json()
                msg = parse_client_message(raw)
                await _handle_message(ws, project, msg)
        finally:
            heartbeat_task.cancel()

    except WebSocketDisconnect:
        logger.info("Client disconnected from project %s", project_id)
    except asyncio.TimeoutError:
        logger.warning("Auth timeout, closing connection")
        await ws.close(code=4000, reason="Auth timeout")
    except Exception:
        logger.exception("WebSocket error for project %s", project_id)
        try:
            await ws.send_json(
                ErrorMessage(message="Internal server error", recoverable=False).model_dump()
            )
        except Exception:
            pass
    finally:
        if project_id:
            await manager.disconnect(project_id)


async def _send_state_sync(ws: WebSocket, project: ProjectState) -> None:
    tail = conv.tail_messages(project.project_dir, project.current_step, count=20)

    # Check for pending confirm
    from mycroft.server.agents.tools.user_confirm import get_pending_confirm
    pending = get_pending_confirm(project.project_id)

    steps = [
        ProtoStepState(step_id=s.step_id, status=s.status)
        for s in project.steps.values()
    ]

    sync = StateSyncMessage(
        project_id=project.project_id,
        project_name=project.project_name,
        current_step=project.current_step,
        steps=steps,
        conversation_tail=tail,
        pending_confirm=pending,
    )
    await ws.send_json(sync.model_dump())


async def _handle_message(ws: WebSocket, project: ProjectState, msg: Any) -> None:
    if msg.type == "message":
        await _handle_user_message(ws, project, msg.text)
    elif msg.type == "command":
        await _handle_command(ws, project, msg.name, msg.args)
    elif msg.type == "confirm_response":
        await _handle_confirm_response(project, msg)
    elif msg.type == "worker_command":
        await _handle_worker_command(project, msg)
    elif msg.type == "pong":
        pass  # heartbeat ack


async def _handle_user_message(ws: WebSocket, project: ProjectState, text: str) -> None:
    # Persist user message
    conv.append_message(
        project.project_dir, project.current_step, {"role": "user", "content": text}
    )

    # Get agent for current step and run
    agent = get_agent(project)
    try:
        await agent.run(text)
    except Exception:
        logger.exception("Agent error in step %s", project.current_step.value)
        await manager.send(
            project.project_id,
            ErrorMessage(message="Agent encountered an error. Please try again."),
        )

    await manager.send(project.project_id, TurnComplete())


async def _handle_command(
    ws: WebSocket, project: ProjectState, name: str, args: dict[str, Any]
) -> None:
    try:
        if name == "next":
            from_step = project.current_step
            new_step = pipeline.advance(project)
            await manager.send(
                project.project_id,
                StepTransition(
                    from_step=from_step,
                    to_step=new_step,
                    to_status=project.steps[new_step].status,
                ),
            )
            # Re-send state sync after transition
            project = ProjectState.load(project.project_id)
            await _send_state_sync(ws, project)

        elif name == "back":
            target = args.get("target")
            if not target:
                await manager.send(
                    project.project_id,
                    ErrorMessage(message="Usage: /back <step_id>"),
                )
                return
            target_step = StepId(target)
            new_step = pipeline.go_back(project, target_step)
            project = ProjectState.load(project.project_id)
            await _send_state_sync(ws, project)

        elif name == "status":
            await _send_state_sync(ws, project)

        elif name == "pause":
            await ws.close(code=1000, reason="User paused")

        elif name == "name":
            new_name = args.get("name", "").strip()
            if new_name:
                project.project_name = new_name
                project.save()
                await _send_state_sync(ws, project)

        else:
            await manager.send(
                project.project_id,
                ErrorMessage(message=f"Unknown command: {name}"),
            )
    except PipelineError as e:
        await manager.send(
            project.project_id,
            ErrorMessage(message=str(e)),
        )


async def _handle_confirm_response(project: ProjectState, msg: ConfirmResponse) -> None:
    from mycroft.server.agents.tools.user_confirm import resolve_confirm
    resolve_confirm(project.project_id, msg.confirm_id, msg.approved, msg.comment)


async def _handle_worker_command(project: ProjectState, msg: Any) -> None:
    """Route worker commands to the orchestrator (if active)."""
    from mycroft.server.agents.execution_dashboard import get_orchestrator

    action = msg.action
    logger.info("Worker command: %s for project %s", action, project.project_id)

    orchestrator = get_orchestrator(project.project_id)
    if orchestrator is None:
        await manager.send(
            project.project_id,
            ErrorMessage(message="No active execution for this project."),
        )
        return

    if action == "pause_all":
        orchestrator.pause_all()
    elif action == "resume_all":
        orchestrator.resume_all()
    elif action == "pause_service":
        if not msg.service_name:
            await manager.send(
                project.project_id,
                ErrorMessage(message="pause_service requires a service_name."),
            )
            return
        if not orchestrator.pause_service(msg.service_name):
            await manager.send(
                project.project_id,
                ErrorMessage(message=f"Service '{msg.service_name}' not found."),
            )
            return
    elif action == "resume_service":
        if not msg.service_name:
            await manager.send(
                project.project_id,
                ErrorMessage(message="resume_service requires a service_name."),
            )
            return
        if not orchestrator.resume_service(msg.service_name):
            await manager.send(
                project.project_id,
                ErrorMessage(message=f"Service '{msg.service_name}' not found."),
            )
            return
    elif action == "cancel":
        await orchestrator.shutdown()
    else:
        await manager.send(
            project.project_id,
            ErrorMessage(message=f"Unknown worker action: {action}"),
        )
        return

    # Send batch status after each successful action
    from mycroft.shared.protocol import WorkerBatchUpdate

    await manager.send(
        project.project_id,
        WorkerBatchUpdate(
            total_tasks=orchestrator.state.total_tasks,
            queued=orchestrator.state.queued,
            running=orchestrator.state.running,
            succeeded=orchestrator.state.succeeded,
            failed=orchestrator.state.failed,
            blocked=orchestrator.state.blocked,
        ),
    )
