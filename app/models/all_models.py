# -*- coding: utf-8 -*-
# app/models/all_models.py
# S_GLOBAL_Dominion - Digital Citadel Core Models v16.0 Nexus

import datetime as dt
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import (
    Column, Integer, String, Float, Numeric, Boolean, 
    Text, ForeignKey, DateTime, Date, Enum, JSON, Index, text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base

# =================================================================
# 0. ENUM ТИПЫ (Константы Вселенной)
# =================================================================

class OwnershipType(str, PyEnum):
    SUBLEASE = "sublease"           # 42 авто (4% + фикс)
    CONNECTED = "connected"         # 78 авто (3%)
    OWNED_5T = "owned_5t"           # Собственный 5-тонник ВкусВилл
    PARTNER_GAZELLE = "partner_gazelle" # Наемные газели партнеров

class TripStatus(str, PyEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class MedicalCheckType(str, PyEnum):
    PRE_TRIP = "pre_trip"
    POST_TRIP = "post_trip"
    PERIODIC = "periodic"
    EXTRAORDINARY = "extraordinary"

class TechnicalCheckType(str, PyEnum):
    PRE_TRIP = "pre_trip"
    POST_TRIP = "post_trip"
    MAINTENANCE = "maintenance"
    DEFECT = "defect"

class BriefingType(str, PyEnum):
    INTRODUCTORY = "introductory"
    PRE_TRIP = "pre_trip"
    SEASONAL = "seasonal"
    SPECIAL = "special"
    UNSCHEDULED = "unscheduled"

# =================================================================
# 1. ИЕРАРХИЯ ВЛАСТИ (User & RBAC)
# =================================================================

class UserRole(str, PyEnum):
    MASTER = "master"
    DIRECTOR = "director"
    ADMIN = "admin"
    CONVOY_HEAD = "convoy_head"
    MANAGER = "manager"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    photo_url = Column(String, nullable=True)
    role = Column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        default=UserRole.MANAGER,
    )
    rating = Column(Float, default=5.0)
    park_name = Column(String, default="PRO")  # Парк: PRO, GO, PLUS, EXPRESS
    
    # Тумблеры доступа Мастера
    can_see_treasury = Column(Boolean, default=False)
    can_see_fleet = Column(Boolean, default=False)
    can_see_analytics = Column(Boolean, default=False)
    can_see_logistics = Column(Boolean, default=False)
    can_see_hr = Column(Boolean, default=False)
    can_edit_users = Column(Boolean, default=False)
    
    language = Column(String, default="ru")
    theme = Column(String, default="luxury")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.now) 
    last_active_at = Column(DateTime, nullable=True)
    is_archived = Column(Boolean, default=False)
    is_core_active = Column(Boolean, default=False)
    
    # REAL-TIME STATUS: Синхронизация с Яндекс.Флот
    realtime_status = Column(String, default="offline")  # online, busy, offline
    work_status = Column(String, default="not_working")  # working, not_working, blocked
    
    # ВОДИТЕЛИ: Математика Эконома/Комфорта (для расчёта дохода)
    yandex_driver_id = Column(String, unique=True, nullable=True)  # ID водителя в Яндексе
    yandex_contractor_id = Column(String, nullable=True, index=True)  # contractor_profile_id
    driver_class = Column(String, default="economy")  # economy, comfort, comfort_plus, business
    daily_rent = Column(Float, default=2000.0)  # Сколько сдаёт водитель (2000, 2500, 3500, 5000)
    base_cost = Column(Float, default=1600.0)  # Себестоимость (1600, 2200, 3000, 4000)
    driver_balance = Column(Float, default=0.0)  # Баланс из Яндекса
    current_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)  # Текущий автомобиль
    current_vehicle = relationship("Vehicle", foreign_keys=[current_vehicle_id])
    
    # ЯНДЕКС.ДИСПЕТЧЕРСКАЯ — Поля синхронизации v35.1
    yandex_work_status = Column(String(50), nullable=True)  # working, not_working, fired, blocked (из API)
    yandex_balance_updated_at = Column(DateTime, nullable=True)  # Время обновления баланса
    yandex_rating = Column(Float, nullable=True)  # Рейтинг из Яндекса
    yandex_phones = Column(JSONB, default=list)  # Телефоны из Яндекса: ["+79001234567", ...]
    yandex_names = Column(JSONB, default=dict)  # ФИО из Яндекса: {"first_name": "Иван", ...}
    yandex_current_car = Column(JSONB, default=dict)  # Машина из Яндекса: {"car_id": "xxx", "car_number": "А123БВ777"}
    yandex_last_sync_at = Column(DateTime, nullable=True)  # Время последней синхронизации
    
    # ДОКУМЕНТЫ ВОДИТЕЛЯ — ВУ (Водительское удостоверение) v35.1
    # Данные из Яндекс API: /v2/parks/contractors/driver-profile → driver_license
    license_number = Column(String(30), nullable=True)  # Серия и номер ВУ (напр. "7722 123456")
    license_issue_date = Column(Date, nullable=True)  # Дата выдачи ВУ
    license_expiry_date = Column(Date, nullable=True)  # Срок окончания ВУ
    license_country = Column(String(10), nullable=True)  # Страна выдачи (rus, etc.)
    driving_experience_from = Column(Date, nullable=True)  # Водительский стаж с (дата)
    
    # Расширенные данные профиля из Яндекс API
    birth_date = Column(Date, nullable=True)  # Дата рождения
    hire_date = Column(Date, nullable=True)  # Дата принятия в парк
    first_order_date = Column(Date, nullable=True)  # Дата первого заказа
    balance_limit = Column(Float, default=5.0)  # Лимит баланса из Яндекса
    
    # JSONB для гибкого хранения доп. документов (будущее: ИИ-проверка)
    driver_documents = Column(JSONB, default=dict)  # {"passport": {...}, "medical": {...}, "other": [...]}
    
    # Связи
    reports = relationship("StaffReport", back_populates="user")
    calls = relationship("CallLog", back_populates="user")
    installments = relationship("FineInstallment", back_populates="driver")
    tension_history = relationship("DriverTensionHistory", back_populates="driver")
    referrals_made = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referral_info = relationship("Referral", foreign_keys="Referral.referral_id", back_populates="referral_user", uselist=False)
    trips_as_driver = relationship("TripSheet", foreign_keys="[TripSheet.driver_id]", back_populates="driver")
    medical_checks = relationship("MedicalCheck", foreign_keys="[MedicalCheck.driver_id]", back_populates="driver")
    briefings = relationship("Briefing", foreign_keys="[Briefing.driver_id]", back_populates="driver")
    
    # Персонал
    technical_checks_as_mechanic = relationship("TechnicalCheck", foreign_keys="[TechnicalCheck.mechanic_id]", back_populates="mechanic")
    medical_checks_as_staff = relationship("MedicalCheck", foreign_keys="[MedicalCheck.medical_staff_id]", back_populates="medical_staff")
    briefings_as_instructor = relationship("Briefing", foreign_keys="[Briefing.instructor_id]", back_populates="instructor")

# =================================================================
# 2. АКТИВЫ (Fleet)
# =================================================================



class RentalTariff(Base):
    __tablename__ = "rental_tariffs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)    # Напр: "Эконом Стандарт"
    car_class = Column(String, nullable=False)           # economy, comfort, comfort_plus
    rent_to_driver = Column(Float, nullable=False)       # Сдаем водителю (2000)
    base_cost_to_partner = Column(Float, nullable=False)   # Берем себе (1600)
    description = Column(String, nullable=True)          # Описание (почему такая цена)
    created_at = Column(DateTime, default=datetime.now)

    # Связь с машинами
    vehicles = relationship("Vehicle", back_populates="tariff")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    model = Column(String)         
    license_plate = Column(String, unique=True, index=True) 
    vin = Column(String, nullable=True)  # VIN 17 символов — без ограничения VARCHAR для надёжности
    
    # ДЕТАЛИ ИЗ ЯНДЕКС API (v30.1)
    color = Column(String, nullable=True)           # Цвет
    year = Column(Integer, nullable=True)           # Год выпуска
    sts_number = Column(String, nullable=True)      # СТС номер
    callsign = Column(String, nullable=True)        # Позывной
    owner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)  # Владелец
    
    # ФИНАНСОВАЯ КАТЕГОРИЗАЦИЯ v20.0
    ownership_type = Column(Enum(OwnershipType), default=OwnershipType.CONNECTED)
    commission_rate = Column(Float, default=0.03)  # Процент комиссии (3% или 4%)
    fixed_fee = Column(Float, default=0.0)  # Фикса (450₽ для субаренды)
    park_name = Column(String, default="PRO")  # Парк: PRO, GO, PLUS, EXPRESS (категория)
    is_park_car = Column(Boolean, default=False)  # True = Владелец "Таксопарк" (rent_type: park)
    tariff_id = Column(Integer, ForeignKey("rental_tariffs.id"), nullable=True)  # Связь с тарифом
    is_active = Column(Boolean, default=True)  # Активна ли машина
    is_free = Column(Boolean, default=True)  # Свободна ли машина (нет водителя)
    
    # СТАТУС И ЭФФЕКТИВНОСТЬ
    status = Column(String, default="working") # working, service, debt_lock, preparing, no_driver, offline
    current_driver_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Текущий водитель
    driver = relationship("User", foreign_keys=[current_driver_id])
    current_mileage = Column(Float, default=0.0)
    next_service_km = Column(Float, default=10000.0)
    yandex_car_id = Column(String, nullable=True, index=True)  # ID машины в Яндексе
    yandex_driver_id = Column(String, nullable=True, index=True)  # ID водителя в Яндексе (для сцепки)
    last_update = Column(DateTime, default=dt.datetime.now)
    created_at = Column(DateTime, default=dt.datetime.now)  # Дата добавления в парк
    
    # PROTOCOL "THE LIVE 300" v200.1 — Имперское Ядро
    is_active_dominion = Column(Boolean, default=False, index=True)  # True = входит в "Живых 300"
    last_transaction_at = Column(DateTime, nullable=True)  # Последняя доходная транзакция
    
    # ЯНДЕКС.ДИСПЕТЧЕРСКАЯ — Поля синхронизации v31.0
    yandex_status = Column(String(50), nullable=True)  # working, not_working (из API)
    yandex_rental = Column(Boolean, nullable=True)  # True = парковый (субаренда), False = подключённый
    yandex_last_sync_at = Column(DateTime, nullable=True)  # Время последней синхронизации
    yandex_park_id = Column(String(100), nullable=True)  # ID парка в Яндексе (PRO, GO, PLUS, EXPRESS)
    
    repairs = relationship("VehicleRepairHistory", back_populates="vehicle")
    trip_sheets = relationship("TripSheet", back_populates="vehicle")
    technical_checks = relationship("TechnicalCheck", back_populates="vehicle")
    tariff = relationship("RentalTariff", back_populates="vehicles")

class VehicleRepairHistory(Base):
    __tablename__ = "vehicle_repair_history"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"))
    parts_json = Column(JSONB, nullable=True) 
    description = Column(Text, nullable=False)
    repair_cost = Column(Float, default=0.0)
    status = Column(String, default="in_service") 
    created_at = Column(DateTime, default=dt.datetime.now)
    
    vehicle = relationship("Vehicle", back_populates="repairs")

class VehicleStatusHistory(Base):
    """История изменений статусов автомобилей (v30.1)"""
    __tablename__ = "vehicle_status_history"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String(100), nullable=True)
    changed_at = Column(DateTime, default=dt.datetime.now, index=True)
    reason = Column(Text, nullable=True)

class VehicleProfile(Base):
    """ГАРАЖ v20.0: Полная анкета автомобиля"""
    __tablename__ = "vehicle_profiles"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), unique=True)
    
    # Документы и Даты
    osago_number = Column(String, nullable=True)
    osago_expiry = Column(Date, nullable=True, index=True)
    kasko_number = Column(String, nullable=True)
    kasko_expiry = Column(Date, nullable=True, index=True)
    license_expiry = Column(Date, nullable=True, index=True)
    diagnostic_card_expiry = Column(Date, nullable=True, index=True)
    
    # Сервис и ТО
    last_to_date = Column(Date, nullable=True)
    next_to_date = Column(Date, nullable=True, index=True)
    to_interval_km = Column(Integer, default=10000)
    
    # Путевые листы и Акты
    trip_sheets_count = Column(Integer, default=0)
    acceptance_acts_count = Column(Integer, default=0)
    
    # Метаданные
    created_at = Column(DateTime, default=dt.datetime.now)
    updated_at = Column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

class ContractTerm(Base):
    """ГИБКОЕ УПРАВЛЕНИЕ АКТИВАМИ: условия аренды и статусы"""
    __tablename__ = "contract_terms"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    park_name = Column(String, default="PRO", index=True)
    is_default = Column(Boolean, default=False, index=True)
    
    # Параметры партнера и водителя
    partner_daily_rent = Column(Float, default=0.0)  # Сколько парк платит владельцу
    driver_daily_rent = Column(Float, default=0.0)   # Сколько водитель платит парку
    commission_rate = Column(Float, default=0.03)    # Комиссия парка
    day_off_rate = Column(Float, default=0.0)        # Льготная ставка выходного
    
    # Статусы исключений
    is_repair = Column(Boolean, default=False)
    is_day_off = Column(Boolean, default=False)
    is_idle = Column(Boolean, default=False)
    
    meta = Column(JSONB, default={})
    created_at = Column(DateTime, default=dt.datetime.now)
    updated_at = Column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

class ContractTermHistory(Base):
    """История изменений контрактных условий"""
    __tablename__ = "contract_term_history"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    contract_term_id = Column(Integer, ForeignKey("contract_terms.id", ondelete="CASCADE"), nullable=False, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=True, index=True)
    changed_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_by = Column(String(100), nullable=True)
    changes = Column(JSONB, default={})
    note = Column(Text, nullable=True)
    changed_at = Column(DateTime, default=dt.datetime.now, index=True)

class FinancialLog(Base):
    """Финансовый лог автосписаний и операций"""
    __tablename__ = "financial_log"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    park_name = Column(String, default="PRO", index=True)
    entry_type = Column(String, default="auto_deduction")
    amount = Column(Float, default=0.0)
    note = Column(Text, nullable=True)
    meta = Column(JSONB, default={})
    created_at = Column(DateTime, default=dt.datetime.now, index=True)

class Partner(Base):
    """ПАРТНЁРЫ v20.0: Инвесторы и владельцы машин"""
    __tablename__ = "partners"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True)
    telegram_id = Column(String, nullable=True)
    
    # Доступ
    login_code = Column(String, nullable=True)
    last_login = Column(DateTime, nullable=True)
    
    # Метаданные
    created_at = Column(DateTime, default=dt.datetime.now)
    is_active = Column(Boolean, default=True)

class PartnerLedger(Base):
    """ПАРТНЕРСКАЯ БУХГАЛТЕРИЯ v20.0"""
    __tablename__ = "partner_ledger"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), index=True)
    
    # Финансы
    incoming = Column(Float, default=0.0)  # Доход от машины (после S-GLOBAL комиссии)
    outgoing = Column(Float, default=0.0)  # Расходы (ТО, запчасти, штрафы)
    
    # Детализация расходов
    expense_type = Column(String, nullable=True)  # "TO", "Parts", "Fine", "OSAGO", etc.
    expense_description = Column(Text, nullable=True)
    
    # Статус машины
    vehicle_status = Column(String, default="active")  # active, idle, service
    daily_rate_applied = Column(Float, nullable=True)  # Фикса применённая (450₽ или 0 при простое)
    
    # Время
    date = Column(Date, index=True)
    created_at = Column(DateTime, default=dt.datetime.now)

class DriverProfile(Base):
    """ГАРАЖ v20.0: Профиль водителя"""
    __tablename__ = "driver_profiles"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Документы
    license_number = Column(String, unique=True, index=True)
    license_expiry = Column(Date, nullable=True, index=True)
    medical_expiry = Column(Date, nullable=True, index=True)
    
    # Статистика и Эффективность
    total_trips = Column(Integer, default=0)
    total_earnings = Column(Float, default=0.0)
    online_time_seconds = Column(Integer, default=0)
    tension_index = Column(Float, default=0.0)
    
    # Yandex Integration
    yandex_driver_id = Column(String, nullable=True, index=True)
    
    # ЯНДЕКС.ДИСПЕТЧЕРСКАЯ — Поля синхронизации v31.0
    yandex_balance = Column(Float, default=0.0)  # Баланс из Яндекса
    yandex_rating = Column(Float, nullable=True)  # Рейтинг из Яндекса
    yandex_work_status = Column(String(50), nullable=True)  # working, not_working, fired, blocked
    yandex_last_sync_at = Column(DateTime, nullable=True)  # Время последней синхронизации
    
    # Уведомления
    last_notification = Column(DateTime, nullable=True)
    
    # Метаданные
    created_at = Column(DateTime, default=dt.datetime.now)
    updated_at = Column(DateTime, default=dt.datetime.now, onupdate=dt.datetime.now)

# =================================================================
# 3. ФИНАНСЫ (Kazna & Интеллектуальный Арбитраж)
# =================================================================

class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index('uq_tx_park_yandex_id', 'park_name', 'yandex_tx_id', unique=True, postgresql_where=text("yandex_tx_id IS NOT NULL")),
        {'extend_existing': True},
    )

    id = Column(Integer, primary_key=True, index=True)
    park_name = Column(String, default="PRO")
    yandex_tx_id = Column(String, nullable=True, index=True)  # Уникальный ID транзакции из Yandex API
    yandex_driver_id = Column(String, nullable=True, index=True)
    category_type = Column(String, nullable=True)  # REVENUE/EXPENSES/PAYOUT/OTHER
    created_at = Column(DateTime, default=dt.datetime.now)
    category = Column(String)              # Yandex_Import, SubRent, VkusVill, Salary, Expense
    contractor = Column(String)            # Контрагент
    description = Column(String)           # Описание
    plate_info = Column(String, nullable=True)  # Гос.номер (если применимо)
    amount = Column(Float)                 # Сумма транзакции
    tx_type = Column(String, default="income")  # income, expense, transfer
    date = Column(DateTime, default=dt.datetime.now)  # Дата операции
    responsibility = Column(String, default="park")  # driver, partner, park
    is_debt_repayment = Column(Boolean, default=False)  # Признак погашения долга

class FineInstallment(Base):
    __tablename__ = "fine_installments"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    total_debt_amount = Column(Numeric(12, 2), nullable=False)
    remaining_debt = Column(Numeric(12, 2), nullable=False)
    daily_deduction_default = Column(Numeric(12, 2), nullable=False) 
    
    status = Column(String, default="grace_period") # grace_period, active, paid
    is_frozen = Column(Boolean, default=False)
    freeze_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.now)
    
    driver = relationship("User", back_populates="installments")

class DriverTensionHistory(Base):
    __tablename__ = "driver_tension_history"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    tension_index = Column(Float, nullable=False)
    calculated_at = Column(DateTime, default=dt.datetime.now)
    
    driver = relationship("User", back_populates="tension_history")

# =================================================================
# 4. СПЕЦИАЛЬНЫЕ ПРОВЕРКИ (КИС АРТ)
# =================================================================

class MedicalCheck(Base):
    __tablename__ = "medical_checks"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    medical_staff_id = Column(Integer, ForeignKey("users.id"))
    check_type = Column(Enum(MedicalCheckType), nullable=False)
    check_time = Column(DateTime, default=dt.datetime.now)
    blood_pressure = Column(String(20))
    alcohol_test = Column(Boolean, default=False)
    is_fit = Column(Boolean, nullable=False)
    
    driver = relationship("User", foreign_keys=[driver_id], back_populates="medical_checks")
    medical_staff = relationship("User", foreign_keys=[medical_staff_id], back_populates="medical_checks_as_staff")
    trip_sheets = relationship("TripSheet", back_populates="medical_check")

class TechnicalCheck(Base):
    __tablename__ = "technical_checks"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    mechanic_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    check_type = Column(Enum(TechnicalCheckType), nullable=False)
    check_time = Column(DateTime, default=dt.datetime.now)
    is_passed = Column(Boolean, nullable=False)
    
    vehicle = relationship("Vehicle", back_populates="technical_checks")
    mechanic = relationship("User", foreign_keys=[mechanic_id], back_populates="technical_checks_as_mechanic")
    trip_sheets = relationship("TripSheet", back_populates="technical_check")

class Briefing(Base):
    __tablename__ = "briefings"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    briefing_type = Column(Enum(BriefingType), nullable=False)
    topic = Column(String(500), nullable=False)
    is_passed = Column(Boolean, default=True)
    
    driver = relationship("User", foreign_keys=[driver_id], back_populates="briefings")
    instructor = relationship("User", foreign_keys=[instructor_id], back_populates="briefings_as_instructor")
    trip_sheets = relationship("TripSheet", back_populates="briefing")

# =================================================================
# 5. СЕРДЦЕ ЛОГИСТИКИ (TripSheet)
# =================================================================

class TripSheet(Base):
    __tablename__ = "trip_sheets"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    trip_number = Column(String(50), unique=True, index=True, nullable=False)
    driver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    
    start_time = Column(DateTime, nullable=False)
    actual_end_time = Column(DateTime)
    start_location = Column(String(500), nullable=False)
    start_odometer = Column(Integer, nullable=False)
    
    medical_check_id = Column(Integer, ForeignKey("medical_checks.id"))
    technical_check_id = Column(Integer, ForeignKey("technical_checks.id"))
    briefing_id = Column(Integer, ForeignKey("briefings.id"))
    
    kis_art_required = Column(Boolean, default=True)
    kis_art_sent = Column(Boolean, default=False)
    kis_art_response = Column(JSONB) 
    
    status = Column(Enum(TripStatus), default=TripStatus.DRAFT, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.now)

    driver = relationship("User", foreign_keys=[driver_id], back_populates="trips_as_driver")
    vehicle = relationship("Vehicle", back_populates="trip_sheets")
    medical_check = relationship("MedicalCheck", back_populates="trip_sheets")
    technical_check = relationship("TechnicalCheck", back_populates="trip_sheets")
    briefing = relationship("Briefing", back_populates="trip_sheets")

# =================================================================
# 6. СКЛАД, AI & РЕФЕРАЛЫ
# =================================================================

class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = {'extend_existing': True}
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    referral_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    status = Column(String, default="pending") 
    reward_amount = Column(Float, default=2000.0)
    required_trips = Column(Integer, default=50)
    current_trips = Column(Integer, default=0)
    created_at = Column(DateTime, default=dt.datetime.now)
    paid_at = Column(DateTime, nullable=True)
    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_made")
    referral_user = relationship("User", foreign_keys=[referral_id], back_populates="referral_info")

class WarehouseItem(Base):
    __tablename__ = "warehouse_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    sku = Column(String, unique=True, index=True)
    category = Column(String)
    quantity = Column(Integer, default=0)
    min_threshold = Column(Integer, default=5)
    price_unit = Column(Float)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class WarehouseLog(Base):
    __tablename__ = "warehouse_logs"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("warehouse_items.id"))
    change = Column(Integer)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    master_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # Реальное поле в БД
    timestamp = Column(DateTime, server_default=func.now())

# =================================================================
# ГЛУБИНА: ПОСТАВЩИКИ И ЗАКАЗ-НАРЯДЫ (v22.6)
# =================================================================

class Supplier(Base):
    """
    Поставщики запчастей и услуг (v22.6 ГЛУБИНА)
    """
    __tablename__ = "suppliers"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)  # ООО "Автозапчасти Плюс"
    contact_person = Column(String)
    phone = Column(String)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    inn = Column(String, nullable=True)
    delivery_days = Column(Integer, default=3)
    min_order_amount = Column(Float, default=0.0)
    rating = Column(Float, default=5.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=dt.datetime.now)
    notes = Column(Text, nullable=True)

class ServiceOrder(Base):
    """
    Заказ-наряд на обслуживание (v22.6 ГЛУБИНА)
    """
    __tablename__ = "service_orders"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False)  # ЗН-20260128-001
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    mechanic_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Детали заказа
    description = Column(Text)  # Описание работ
    parts_json = Column(JSONB, default=[])  # Список запчастей
    labor_cost = Column(Float, default=0.0)  # Стоимость работы
    parts_cost = Column(Float, default=0.0)  # Стоимость запчастей
    total_cost = Column(Float, default=0.0)  # Итого
    
    # Статус
    status = Column(String, default="draft")  # draft, in_progress, completed, cancelled
    
    # Пробег
    mileage_in = Column(Integer, nullable=True)  # При приёмке
    mileage_out = Column(Integer, nullable=True)  # При выдаче
    
    # Временные метки
    created_at = Column(DateTime, default=dt.datetime.now)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Примечания
    notes = Column(Text, nullable=True)
    pdf_path = Column(String, nullable=True)  # Путь к PDF заказ-наряда

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String)  # "user" | "assistant"
    content = Column(Text)
    group_name = Column(String, default="ОБЩАЯ")  # ОБЩАЯ, ФЛОТ, ФИНАНСЫ, ПЛАНИРОВАНИЕ
    thread_id = Column(String, nullable=True)  # Идентификатор треда
    parent_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=True)  # Ответ в треде
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    attachments = Column(JSONB, default=[])  # Привязанные объекты (машины/транзакции)
    file_path = Column(String, nullable=True)  # Путь к загруженному файлу
    is_read = Column(Boolean, default=False, index=True)  # Прочитано ли сообщение
    timestamp = Column(DateTime, default=dt.datetime.now)
    created_at = Column(DateTime, default=dt.datetime.now, index=True)

class OracleArchive(Base):
    __tablename__ = "oracle_archive"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="AI Watcher")
    channel = Column(String, default="MASTER")
    content = Column(Text)
    severity = Column(String, default="info")
    meta = Column(JSONB, default={})
    created_at = Column(DateTime, default=dt.datetime.now, index=True)

class CallLog(Base):
    __tablename__ = "call_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    phone_number = Column(String)
    ai_rating = Column(Integer, default=5)
    timestamp = Column(DateTime, default=dt.datetime.now)
    user = relationship("User", back_populates="calls")

class StaffReport(Base):
    __tablename__ = "staff_reports"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    stars = Column(Integer) 
    date = Column(Date, default=dt.date.today)
    user = relationship("User", back_populates="reports")

# =================================================================
# ЯНДЕКС.ДИСПЕТЧЕРСКАЯ — Лог синхронизаций v31.0
# =================================================================

class YandexSyncLog(Base):
    """Лог синхронизаций с Яндекс.Диспетчерской"""
    __tablename__ = "yandex_sync_log"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, index=True)
    sync_type = Column(String(50), nullable=False)  # vehicles, drivers, transactions
    park_id = Column(String(100), nullable=False, index=True)  # PRO, GO, PLUS, EXPRESS
    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    error_details = Column(JSONB, default=list)  # Массив ошибок
    started_at = Column(DateTime, nullable=False, index=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

# =================================================================
# ЭКСПОРТ ВСЕХ МОДЕЛЕЙ
# =================================================================

# Импорт CRM моделей

__all__ = [
    "User", "Transaction", "FineInstallment", "DriverTensionHistory",
    "Vehicle", "VehicleRepairHistory", "VehicleProfile", "DriverProfile",
    "ContractTerm", "ContractTermHistory", "FinancialLog",
    "ChatMessage", "CallLog", "StaffReport",
    "TripSheet", "TripStatus", "MedicalCheck", "MedicalCheckType",
    "TechnicalCheck", "TechnicalCheckType", "Briefing", "BriefingType",
    "Referral", "WarehouseItem", "WarehouseLog", "OwnershipType",
    "Supplier", "ServiceOrder",  # v22.6 ERP
    "YandexSyncLog",  # v31.0 Яндекс.Диспетчерская
]
