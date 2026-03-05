# -*- coding: utf-8 -*-
# app/api/v1/merit.py

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.services.security import get_current_user_optional

router = APIRouter(tags=["Merit"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/merit")
async def merit_page(request: Request, current_user = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "modules/merit.html",
        {"request": request, "current_user": current_user}
    )
