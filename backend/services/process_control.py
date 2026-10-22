"""Cancellation of request handlers and durable background jobs (single worker)."""
import asyncio
from contextvars import ContextVar
from fastapi import HTTPException, Request
from fastapi.routing import APIRoute

requests: dict[str, tuple[str, asyncio.Task, str]] = {}
jobs: dict[str, asyncio.Task] = {}
workspace_scope = ContextVar("workspace_scope", default=None)
job_scopes: dict[str, tuple[str, str] | None] = {}
cancelled_jobs: set[str] = set()
resetting_scopes: set[tuple[str, str]] = set()


def request_scope(request):
    owner = request.headers.get("authorization") or request.cookies.get("atos_workspace", "")
    return owner, request.headers.get("x-workspace-id", "")


class CancellableRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def controlled(request: Request):
            scope = request_scope(request)
            token = workspace_scope.set(scope)
            try:
                return await execute(request, scope)
            finally:
                workspace_scope.reset(token)

        async def execute(request, scope):
            key = request.headers.get("x-process-id")
            if scope in resetting_scopes and "/processes/" not in request.url.path:
                raise HTTPException(409, "Process cancelled by workspace reset.")
            if not key or "/processes/" in request.url.path:
                return await handler(request)
            if key in requests:
                raise HTTPException(409, "This process identifier is already in use.")
            task = asyncio.create_task(handler(request))
            requests[key] = (scope[0], task, scope[1])
            try:
                return await task
            except asyncio.CancelledError:
                raise HTTPException(409, "Process cancelled. Completed steps are retained.")
            finally:
                requests.pop(key, None)
        return controlled


def schedule_job(background_tasks, key, function, *args):
    """Capture tab ownership before the request's background response is dispatched."""
    cancelled_jobs.discard(key)
    scope = workspace_scope.get()
    job_scopes[key] = scope
    background_tasks.add_task(run_job, key, function, *args, scope=scope)


async def run_job(key, function, *args, scope=None):
    if key in cancelled_jobs:
        cancelled_jobs.discard(key)
        job_scopes.pop(key, None)
        return
    job_scopes[key] = scope
    task = asyncio.create_task(function(*args))
    jobs[key] = task
    try:
        return await task
    except asyncio.CancelledError:
        pass
    finally:
        jobs.pop(key, None)
        job_scopes.pop(key, None)
        cancelled_jobs.discard(key)


async def cancel_job(key):
    if key in job_scopes:
        cancelled_jobs.add(key)
    task = jobs.get(key)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
