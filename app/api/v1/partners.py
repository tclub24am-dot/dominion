# -*- coding: utf-8 -*-
# app/api/v1/partners.py

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from app.services.security import get_current_user_optional

router = APIRouter(tags=["Partners"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/partners")
async def partners_page(request: Request, current_user = Depends(get_current_user_optional)):
    return templates.TemplateResponse(
        "modules/partners.html",
        {"request": request, "current_user": current_user}
    )
