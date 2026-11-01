"""Workspace HTTP adapters; operations and persistence are separate."""

from fastapi import APIRouter, Depends, Response
from ..request_models import DefaultCoordinator, WorkspaceCreate, Invite, JoinDecision, Listing, MemberEdit
from ..services.workspaces import operations


def install_routes(app, store, scoped, active, workspace_admin):
    service = operations(store, scoped, active, workspace_admin)
    router = APIRouter()

    @router.post("/api/v1/workspaces", status_code=201)
    def create_workspace(body: WorkspaceCreate, current=Depends(active)):
        return service.create_workspace(body=body, current=current)

    @router.post("/api/v1/workspaces/{workspace_id}/invitations", status_code=201)
    def invite(workspace_id: str, body: Invite, current=Depends(active)):
        return service.invite(workspace_id=workspace_id, body=body, current=current)

    @router.patch("/api/v1/workspaces/{workspace_id}/listing")
    def listing(workspace_id: str, body: Listing, current=Depends(active)):
        return service.listing(workspace_id=workspace_id, body=body, current=current)

    @router.patch("/api/v1/workspaces/{workspace_id}/default-coordinator")
    def default_coordinator(workspace_id: str, body: DefaultCoordinator, current=Depends(active)):
        return service.default_coordinator(workspace_id=workspace_id, body=body, current=current)

    @router.get("/api/v1/listed-workspaces")
    def listed_workspaces(current=Depends(active)):
        return service.listed_workspaces(current=current)

    @router.post("/api/v1/workspaces/{workspace_id}/join-requests", status_code=201)
    def ask_to_join(workspace_id: str, current=Depends(active)):
        return service.ask_to_join(workspace_id=workspace_id, current=current)

    @router.get("/api/v1/workspaces/{workspace_id}/join-requests")
    def join_requests(workspace_id: str, current=Depends(active)):
        return service.join_requests(workspace_id=workspace_id, current=current)

    @router.post("/api/v1/workspaces/{workspace_id}/join-requests/{request_id}")
    def decide_join(workspace_id: str, request_id: str, body: JoinDecision, current=Depends(active)):
        return service.decide_join(workspace_id=workspace_id, request_id=request_id, body=body, current=current)

    @router.get("/api/v1/my-invitations")
    def invitations(current=Depends(active)):
        return service.invitations(current=current)

    @router.post("/api/v1/my-invitations/{invitation_id}/accept")
    def accept(invitation_id: str, current=Depends(active)):
        return service.accept(invitation_id=invitation_id, current=current)

    @router.patch("/api/v1/workspaces/{workspace_id}/members/{user_id}")
    def change_role(workspace_id: str, user_id: str, body: MemberEdit, current=Depends(active)):
        return service.change_role(workspace_id=workspace_id, user_id=user_id, body=body, current=current)

    @router.delete("/api/v1/workspaces/{workspace_id}/members/{user_id}", status_code=204)
    def remove_member(workspace_id: str, user_id: str, current=Depends(active)):
        service.remove_member(workspace_id=workspace_id, user_id=user_id, current=current)
        return Response(status_code=204)

    app.include_router(router)
