# -*- coding: utf-8 -*-
# app/api/v1/gps.py

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.services.security import get_current_user_optional

router = APIRouter(tags=["GPS"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/gps")
async def gps_page(request: Request, current_user = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "modules/gps.html",
        {"request": request, "current_user": current_user}
    )
