import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from chargeghost_evse.ocpp_adapter.v201_adapter import V201Adapter
from ocpp.v201.datatypes import CostType, MessageContentType
from ocpp.v201.enums import CostKindEnumType, CustomerInformationStatusEnumType


def _make_adapter(**overrides) -> V201Adapter:
    mock_conn = MagicMock()
    mock_conn.recv = AsyncMock()
    mock_conn.send = AsyncMock()
    kwargs = {
        "id": "CP_1",
        "connection": mock_conn,
        "command_queue": MagicMock(),
        "charge_point_model": "ChargeGhostV2",
        "charge_point_vendor": "ChargeGhost",
    }
    kwargs.update(overrides)
    return V201Adapter(**kwargs)


class TestOnCostUpdated:
    def test_stores_cost_for_transaction(self):
        adapter = _make_adapter()
        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=150,
                amount_multiplier=-2,
            ),
        ]
        result = asyncio.run(
            adapter.on_cost_updated(
                total_cost=costs,
                transaction_id="tx_001",
            )
        )
        assert result is not None
        assert "tx_001" in adapter._transaction_costs
        assert len(adapter._transaction_costs["tx_001"]) == 1
        assert adapter._transaction_costs["tx_001"][0].amount == 150

    def test_stores_multiple_cost_entries(self):
        adapter = _make_adapter()
        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=100,
                amount_multiplier=-2,
            ),
            CostType(
                cost_kind=CostKindEnumType.carbon_dioxide_emission,
                amount=50,
                amount_multiplier=-1,
            ),
        ]
        asyncio.run(
            adapter.on_cost_updated(
                total_cost=costs,
                transaction_id="tx_002",
            )
        )
        assert len(adapter._transaction_costs["tx_002"]) == 2

    def test_logs_cost_updated(self, caplog):
        adapter = _make_adapter()
        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=200,
                amount_multiplier=-2,
            ),
        ]
        with caplog.at_level(logging.INFO, logger="chargeghost.ocpp"):
            asyncio.run(
                adapter.on_cost_updated(
                    total_cost=costs,
                    transaction_id="tx_003",
                )
            )
        assert any("CostUpdated" in r.message for r in caplog.records)

    def test_overwrites_previous_cost(self):
        adapter = _make_adapter()
        costs1 = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=100,
                amount_multiplier=-2,
            ),
        ]
        costs2 = [
            CostType(
                cost_kind=CostKindEnumType.carbon_dioxide_emission,
                amount=50,
                amount_multiplier=-1,
            ),
        ]
        asyncio.run(
            adapter.on_cost_updated(
                total_cost=costs1,
                transaction_id="tx_004",
            )
        )
        asyncio.run(
            adapter.on_cost_updated(
                total_cost=costs2,
                transaction_id="tx_004",
            )
        )
        assert len(adapter._transaction_costs["tx_004"]) == 1
        assert (
            adapter._transaction_costs["tx_004"][0].cost_kind
            == CostKindEnumType.carbon_dioxide_emission
        )


class TestTransactionEventCostStorage:
    def test_started_response_stores_total_cost(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=100,
                amount_multiplier=-2,
            ),
        ]
        mock_response.total_cost = costs
        adapter.call = AsyncMock(return_value=mock_response)

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        assert tx_id in adapter._transaction_costs
        assert adapter._transaction_costs[tx_id] == costs

    def test_updated_response_stores_total_cost(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=200,
                amount_multiplier=-2,
            ),
        ]
        mock_response = MagicMock()
        mock_response.total_cost = costs
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.send_transaction_event_updated(
                connector_id=1,
                transaction_id=tx_id,
                timestamp="2026-01-01T00:01:00Z",
            )
        )

        assert adapter._transaction_costs[tx_id] == costs

    def test_ended_response_stores_total_cost(self):
        adapter = _make_adapter()
        adapter.call = AsyncMock(return_value=MagicMock())

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        costs = [
            CostType(
                cost_kind=CostKindEnumType.carbon_dioxide_emission,
                amount=75,
                amount_multiplier=-1,
            ),
        ]
        mock_response = MagicMock()
        mock_response.total_cost = costs
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.send_transaction_event_ended(
                connector_id=1,
                transaction_id=tx_id,
                timestamp="2026-01-01T01:00:00Z",
                meter_stop=5000,
                reason="Local",
            )
        )

        assert adapter._transaction_costs[tx_id] == costs

    def test_no_cost_when_response_has_none(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.total_cost = None
        adapter.call = AsyncMock(return_value=mock_response)

        _, tx_id = asyncio.run(
            adapter.send_transaction_event_started(
                connector_id=1,
                id_tag="TAG1",
                meter_start=0,
                timestamp="2026-01-01T00:00:00Z",
            )
        )

        assert tx_id not in adapter._transaction_costs


class TestGetTransactionCost:
    def test_returns_stored_cost(self):
        adapter = _make_adapter()
        costs = [
            CostType(
                cost_kind=CostKindEnumType.relative_price_percentage,
                amount=100,
                amount_multiplier=-2,
            ),
        ]
        adapter._transaction_costs["tx_001"] = costs
        result = adapter.get_transaction_cost("tx_001")
        assert result == costs

    def test_returns_none_for_unknown_transaction(self):
        adapter = _make_adapter()
        result = adapter.get_transaction_cost("unknown")
        assert result is None


class TestOnCustomerInformation:
    def test_report_accepted(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_customer_information(
                request_id=1,
                report=True,
                clear=False,
            )
        )
        assert result.status == CustomerInformationStatusEnumType.accepted

    def test_clear_accepted(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_customer_information(
                request_id=2,
                report=False,
                clear=True,
            )
        )
        assert result.status == CustomerInformationStatusEnumType.accepted

    def test_rejected_when_no_report_or_clear(self):
        adapter = _make_adapter()
        result = asyncio.run(
            adapter.on_customer_information(
                request_id=3,
                report=False,
                clear=False,
            )
        )
        assert result.status == CustomerInformationStatusEnumType.rejected

    def test_log_customer_information(self, caplog):
        adapter = _make_adapter()
        with caplog.at_level(logging.INFO, logger="chargeghost.ocpp"):
            asyncio.run(
                adapter.on_customer_information(
                    request_id=4,
                    report=True,
                    clear=False,
                )
            )
        assert any("CustomerInformation" in r.message for r in caplog.records)


class TestSendNotifyCustomerInformation:
    def test_sends_with_data(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        data = [
            MessageContentType(
                format="PLAIN",
                content="Customer details here",
                language="en",
            ),
        ]

        response = asyncio.run(
            adapter.send_notify_customer_information(
                request_id=1,
                data=data,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.request_id == 1
        assert len(request.data) == 1
        assert request.data[0].content == "Customer details here"
        assert response == mock_response

    def test_sends_without_data(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.send_notify_customer_information(
                request_id=2,
            )
        )

        adapter.call.assert_awaited_once()
        request = adapter.call.call_args[0][0]
        assert request.request_id == 2
        assert request.data is None

    def test_send_with_tbc(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        adapter.call = AsyncMock(return_value=mock_response)

        asyncio.run(
            adapter.send_notify_customer_information(
                request_id=3,
                tbc=True,
            )
        )

        request = adapter.call.call_args[0][0]
        assert request.tbc is True


class TestTariffCostCtrlrVariables:
    def test_tariff_cost_ctrlr_has_enabled(self):
        from chargeghost_evse.ocpp_adapter.device_model.device_model import (
            ChargingStationDeviceModel,
        )

        dm = ChargingStationDeviceModel()

        comp = dm.find_component(name="TariffCostCtrlr")
        assert comp is not None
        var = dm.find_variable(comp, "Enabled")
        assert var is not None
        assert var.attributes["Actual"].value == "true"

    def test_tariff_cost_ctrlr_has_available(self):
        from chargeghost_evse.ocpp_adapter.device_model.device_model import (
            ChargingStationDeviceModel,
        )

        dm = ChargingStationDeviceModel()

        comp = dm.find_component(name="TariffCostCtrlr")
        var = dm.find_variable(comp, "Available")
        assert var is not None
        assert var.attributes["Actual"].value == "true"

    def test_tariff_cost_ctrlr_has_currency(self):
        from chargeghost_evse.ocpp_adapter.device_model.device_model import (
            ChargingStationDeviceModel,
        )

        dm = ChargingStationDeviceModel()

        comp = dm.find_component(name="TariffCostCtrlr")
        var = dm.find_variable(comp, "Currency")
        assert var is not None
        assert var.attributes["Actual"].mutability == "ReadWrite"

    def test_tariff_cost_ctrlr_has_fallback_messages(self):
        from chargeghost_evse.ocpp_adapter.device_model.device_model import (
            ChargingStationDeviceModel,
        )

        dm = ChargingStationDeviceModel()

        comp = dm.find_component(name="TariffCostCtrlr")
        assert dm.find_variable(comp, "TariffFallbackMessage") is not None
        assert dm.find_variable(comp, "TotalCostFallbackMessage") is not None
