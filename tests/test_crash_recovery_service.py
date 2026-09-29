"""
Unit tests for CrashRecoveryService (Startup crash reconciliation and dispatch staleness policy).
"""

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.services.crash_recovery_service import (
    CrashRecoveryService,
)
from src.shared.constants import (
    AnalysisStage,
    TaskStatus,
)
from src.utils.time_utils import from_timestamp_local


@pytest.fixture
def mock_trace_store():
    store = MagicMock()
    store.get_crashed_traces_on_startup.return_value = []
    return store


@pytest.fixture
def mock_checkpoint_store():
    store = MagicMock()
    store.get_checkpoint.return_value = None
    return store


@pytest.fixture
def mock_analysis_service():
    service = MagicMock()
    service.resume_analysis = AsyncMock()
    return service


@pytest.fixture
def mock_dispatcher():
    dispatcher = MagicMock()
    dispatcher.dispatch = AsyncMock(return_value=True)
    return dispatcher


@pytest.mark.asyncio
async def test_recover_crashed_tasks_empty(
    mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
):
    service = CrashRecoveryService(
        mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
    )
    result = await service.recover_crashed_tasks()
    assert result == {"recovered": 0, "archived": 0, "aborted": 0}


@pytest.mark.asyncio
async def test_recover_crashed_tasks_same_day_dispatches(
    mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
):
    started_at = dt.datetime.now().timestamp()
    # 期望值必须与实现同源（北京时间）：直接 dt.datetime.now() 取的是 runner 本地时区，
    # 在非 UTC+8 的 CI runner 上会与实现算出的日期差一天，导致误报失败。
    today_str = from_timestamp_local(started_at).strftime("%Y-%m-%d")

    mock_trace_store.get_crashed_traces_on_startup.return_value = [
        {
            "trace_id": "trace_today_1",
            "group_id": "123456",
            "platform": "aiocqhttp",
            "trigger_type": "auto",
            "started_at": started_at,
        }
    ]

    mock_checkpoint_store.get_checkpoint.side_effect = lambda g, d, stage, **kwargs: (
        {"statistics": {}, "unified_messages": []}
        if stage == AnalysisStage.CLEAN_MESSAGES.value
        else None
    )

    mock_analysis_service.resume_analysis.return_value = {
        "success": True,
        "analysis_result": {"statistics": MagicMock(), "topics": []},
        "platform_id": "aiocqhttp",
    }

    service = CrashRecoveryService(
        mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
    )
    result = await service.recover_crashed_tasks()

    assert result == {"recovered": 1, "archived": 0, "aborted": 0}
    mock_analysis_service.resume_analysis.assert_awaited_once_with(
        trace_id="trace_today_1",
        group_id="123456",
        platform_id="aiocqhttp",
        date_str=today_str,
    )
    mock_dispatcher.dispatch.assert_awaited_once_with(
        "123456",
        {
            "statistics": mock_analysis_service.resume_analysis.return_value[
                "analysis_result"
            ]["statistics"],
            "topics": [],
        },
        "aiocqhttp",
    )


@pytest.mark.asyncio
async def test_recover_crashed_tasks_cross_day_silently_archives(
    mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
):
    started_at = (dt.datetime.now() - dt.timedelta(days=1)).timestamp()
    yesterday_str = from_timestamp_local(started_at).strftime("%Y-%m-%d")

    mock_trace_store.get_crashed_traces_on_startup.return_value = [
        {
            "trace_id": "trace_yesterday_1",
            "group_id": "123456",
            "platform": "aiocqhttp",
            "trigger_type": "auto",
            "started_at": started_at,
        }
    ]

    mock_checkpoint_store.get_checkpoint.side_effect = lambda g, d, stage, **kwargs: (
        {"statistics": {}, "unified_messages": []}
        if stage == AnalysisStage.CLEAN_MESSAGES.value
        else None
    )

    mock_analysis_service.resume_analysis.return_value = {
        "success": True,
        "analysis_result": {"statistics": MagicMock(), "topics": []},
        "platform_id": "aiocqhttp",
    }

    service = CrashRecoveryService(
        mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
    )
    result = await service.recover_crashed_tasks()

    assert result == {"recovered": 0, "archived": 1, "aborted": 0}
    mock_analysis_service.resume_analysis.assert_awaited_once_with(
        trace_id="trace_yesterday_1",
        group_id="123456",
        platform_id="aiocqhttp",
        date_str=yesterday_str,
    )
    # Cross-day task must NOT dispatch to the group
    mock_dispatcher.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_recover_crashed_tasks_no_checkpoint_aborted(
    mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
):
    mock_trace_store.get_crashed_traces_on_startup.return_value = [
        {
            "trace_id": "trace_no_cp",
            "group_id": "999888",
            "platform": "aiocqhttp",
            "trigger_type": "manual",
            "started_at": dt.datetime.now().timestamp(),
        }
    ]

    mock_checkpoint_store.get_checkpoint.return_value = None

    service = CrashRecoveryService(
        mock_trace_store, mock_checkpoint_store, mock_analysis_service, mock_dispatcher
    )
    result = await service.recover_crashed_tasks()

    assert result == {"recovered": 0, "archived": 0, "aborted": 1}
    mock_analysis_service.resume_analysis.assert_not_called()
    mock_dispatcher.dispatch.assert_not_called()
    mock_trace_store.save_trace.assert_called_once()
    saved_payload = mock_trace_store.save_trace.call_args[0][0]
    assert saved_payload["trace_id"] == "trace_no_cp"
    assert saved_payload["status"] == TaskStatus.ABORTED.value
