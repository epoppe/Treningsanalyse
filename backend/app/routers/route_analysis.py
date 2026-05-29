from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..dependencies import get_data_storage
from ..services.route_analysis_service import RouteAnalysisService
from ..storage import DataStorage

router = APIRouter(tags=["Route Analysis"])


def get_route_analysis_service(storage: DataStorage = Depends(get_data_storage)) -> RouteAnalysisService:
    return RouteAnalysisService(storage)


@router.post("/routes/recalculate")
def recalculate_routes(
    activity_id: Optional[str] = Query(None, description="Optional Garmin activity ID. If omitted, all outdoor runs are analyzed."),
    limit: Optional[int] = Query(None, ge=1, le=2000, description="Max activities when recalculating all runs."),
    service: RouteAnalysisService = Depends(get_route_analysis_service),
    db: Session = Depends(get_db),
):
    if activity_id:
        return service.analyze_activity(activity_id, db)
    return service.analyze_all_running_routes(db, limit=limit)


@router.get("/routes/matches/{activity_id}")
def get_route_matches(
    activity_id: str,
    same_route_only: bool = Query(True),
    limit: int = Query(20, ge=1, le=200),
    service: RouteAnalysisService = Depends(get_route_analysis_service),
    db: Session = Depends(get_db),
):
    return {
        "activityId": activity_id,
        "matches": service.get_activity_matches(
            activity_id,
            db,
            same_route_only=same_route_only,
            limit=limit,
        ),
    }


@router.get("/routes/groups")
def list_route_groups(
    min_activities: int = Query(2, ge=1, le=100),
    limit: int = Query(50, ge=1, le=500),
    service: RouteAnalysisService = Depends(get_route_analysis_service),
    db: Session = Depends(get_db),
):
    return {
        "groups": service.list_route_groups(
            db,
            min_activities=min_activities,
            limit=limit,
        )
    }

