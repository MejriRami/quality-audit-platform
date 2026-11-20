from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import your Base model
from app.config.database import Base

# Import all your models so Alembic can detect them
# USERS & ROLES
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole

# ENUMS
from app.models.enums import (
    audit_status_enum,
    ca_status_enum,
    plant_type_enum,
    audit_action_enum,
    ca_decision_enum,
)

from app.models.framework import Framework
from app.models.audit_type import AuditType
from app.models.questionnaire import Questionnaire
from app.models.questionnaire_auditor import QuestionnaireAuditor
from app.models.questionnaire_questions import QuestionnaireQuestion

from app.models.question import Question

from app.models.audit import Audit
from app.models.audit_reschedule_history import AuditRescheduleHistory

from app.models.audit_answr import AuditAnswer
from app.models.document import Document
from app.models.audit_auditee import  AuditAuditee

from app.models.corrective_action import CorrectiveAction
from app.models.car_escalation import CarEscalation
from app.models.corrective_action_history import CorrectiveActionHistory
from app.models.portal_chatbot_message import PortalChatbotMessage
# from app.models.kpi_chatbot_message import KpiChatbotMessage
from app.models.correctiveActionEmailOTP import CorrectiveActionEmailOTP
from app.models.correctiveActionsAccessToken import CorrectiveActionAccessToken
from app.models.plant_holiday import PlantHoliday
from app.models.auditor_holiday import AuditorHoliday
from app.models import audit_planning  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option(
        "sqlalchemy.url",
        database_url.replace('%', '%%')
    )
# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
