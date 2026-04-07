"""
tests/test_mercados_client.py

Testes para data/mercados_client.py — wrapper da biblioteca mercados.
Todos os testes usam mocks para não depender de conectividade externa.
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from data.mercados_client import (
    get_b3_dividends,
    get_cvm_daily_report,
    get_fundosnet_documents,
    get_ifix_composition,
)

# ---------------------------------------------------------------------------
# get_ifix_composition
# ---------------------------------------------------------------------------


class TestGetIfixComposition:
    def test_returns_list_when_b3_succeeds(self):
        mock_carteira = [
            {"ticker": "MXRF11", "nome": "Maxi Renda", "participacao": 3.5, "tipo": "FII"},
            {"ticker": "HGLG11.SA", "nome": "CSHG Logística", "participacao": 2.1, "tipo": "FII"},
        ]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.return_value = mock_carteira
            result = get_ifix_composition()

        assert len(result) == 2
        assert result[0]["ticker"] == "MXRF11"
        assert result[0]["peso"] == 3.5
        # .SA suffix stripped
        assert result[1]["ticker"] == "HGLG11"
        assert result[1]["peso"] == 2.1

    def test_returns_empty_list_on_b3_exception(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.side_effect = ConnectionError("timeout")
            result = get_ifix_composition()

        assert result == []

    def test_returns_empty_list_when_mercados_unavailable(self):
        with patch("data.mercados_client.HAS_MERCADOS", False):
            result = get_ifix_composition()

        assert result == []

    def test_handles_empty_carteira(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.return_value = []
            result = get_ifix_composition()

        assert result == []

    def test_normalizes_ticker_uppercase(self):
        mock_carteira = [{"ticker": "knri11", "participacao": 1.0}]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.return_value = mock_carteira
            result = get_ifix_composition()

        assert result[0]["ticker"] == "KNRI11"

    def test_uses_codigo_key_as_fallback(self):
        mock_carteira = [{"codigo": "BCFF11", "participacao": 0.5}]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.return_value = mock_carteira
            result = get_ifix_composition()

        assert result[0]["ticker"] == "BCFF11"

    def test_handles_none_participacao(self):
        mock_carteira = [{"ticker": "XPML11", "participacao": None}]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.carteira_indice.return_value = mock_carteira
            result = get_ifix_composition()

        assert result[0]["peso"] == 0.0


# ---------------------------------------------------------------------------
# get_cvm_daily_report
# ---------------------------------------------------------------------------


class TestGetCvmDailyReport:
    def test_returns_list_from_dataframe(self):
        import pandas as pd

        mock_df = pd.DataFrame(
            [
                {"CNPJ_FUNDO": "12.345.678/0001-90", "VL_QUOTA": 10.5, "NR_COTST": 5000},
                {"CNPJ_FUNDO": "98.765.432/0001-10", "VL_QUOTA": 22.3, "NR_COTST": 12000},
            ]
        )
        with patch("data.mercados_client.CVM") as MockCVM:
            MockCVM.return_value.informe_diario_fundo.return_value = mock_df
            result = get_cvm_daily_report(date=datetime.date(2025, 1, 15))

        assert len(result) == 2
        assert result[0]["CNPJ_FUNDO"] == "12.345.678/0001-90"

    def test_uses_yesterday_as_default_date(self):
        today = datetime.date(2025, 6, 10)
        expected = datetime.date(2025, 6, 9)
        with patch("data.mercados_client.CVM") as MockCVM:
            MockCVM.return_value.informe_diario_fundo.return_value = []
            with patch("data.mercados_client.datetime") as mock_dt:
                mock_dt.date.today.return_value = today
                mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
                mock_dt.timedelta = datetime.timedelta
                get_cvm_daily_report()

            MockCVM.return_value.informe_diario_fundo.assert_called_once_with(expected)

    def test_returns_empty_list_when_report_is_none(self):
        with patch("data.mercados_client.CVM") as MockCVM:
            MockCVM.return_value.informe_diario_fundo.return_value = None
            result = get_cvm_daily_report()

        assert result == []

    def test_returns_empty_list_on_exception(self):
        with patch("data.mercados_client.CVM") as MockCVM:
            MockCVM.return_value.informe_diario_fundo.side_effect = RuntimeError("API error")
            result = get_cvm_daily_report()

        assert result == []

    def test_returns_empty_list_when_mercados_unavailable(self):
        with patch("data.mercados_client.HAS_MERCADOS", False):
            result = get_cvm_daily_report()

        assert result == []

    def test_handles_plain_list_response(self):
        mock_list = [{"CNPJ": "11.111.111/0001-11", "valor": 100.0}]
        with patch("data.mercados_client.CVM") as MockCVM:
            MockCVM.return_value.informe_diario_fundo.return_value = mock_list
            result = get_cvm_daily_report()

        assert result == mock_list


# ---------------------------------------------------------------------------
# get_fundosnet_documents
# ---------------------------------------------------------------------------


class TestGetFundosnetDocuments:
    def _mock_docs(self):
        return [
            {
                "ticker": "MXRF11",
                "categoria": "Informe Mensal",
                "dataEntrega": "2025-03-01",
                "descricao": "Informe de março",
                "url": "https://example.com/doc1",
            },
            {
                "ticker": "HGLG11",
                "categoria": "Comunicado ao Mercado",
                "dataEntrega": "2025-03-05",
                "descricao": "Distribuição de rendimentos",
                "url": "https://example.com/doc2",
            },
        ]

    def test_returns_all_documents_without_ticker_filter(self):
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.return_value = self._mock_docs()
            result = get_fundosnet_documents()

        assert len(result) == 2

    def test_filters_by_ticker(self):
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.return_value = self._mock_docs()
            result = get_fundosnet_documents(ticker="MXRF11")

        assert len(result) == 1
        assert result[0]["ticker"] == "MXRF11"

    def test_ticker_filter_case_insensitive(self):
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.return_value = self._mock_docs()
            result = get_fundosnet_documents(ticker="hglg11")

        assert len(result) == 1
        assert result[0]["ticker"] == "HGLG11"

    def test_uses_default_date_range(self):
        today = datetime.date(2025, 4, 1)
        expected_start = datetime.date(2025, 3, 2)
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.return_value = []
            with patch("data.mercados_client.datetime") as mock_dt:
                mock_dt.date.today.return_value = today
                mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
                mock_dt.timedelta = datetime.timedelta
                get_fundosnet_documents()

            call_kwargs = MockFN.return_value.search.call_args[1]
            assert call_kwargs["end_date"] == today
            assert call_kwargs["start_date"] == expected_start

    def test_returns_empty_list_on_exception(self):
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.side_effect = ConnectionError("timeout")
            result = get_fundosnet_documents()

        assert result == []

    def test_returns_empty_list_when_mercados_unavailable(self):
        with patch("data.mercados_client.HAS_MERCADOS", False):
            result = get_fundosnet_documents()

        assert result == []

    def test_normalizes_doc_fields(self):
        docs = [
            {
                "codigo": "KNRI11",
                "tipo": "Ata",
                "data": "2025-02-10",
                "descricao": "Ata de assembleia",
                "url": "https://example.com/ata",
            }
        ]
        with patch("data.mercados_client.FundosNet") as MockFN:
            MockFN.return_value.search.return_value = docs
            result = get_fundosnet_documents()

        assert result[0]["ticker"] == "KNRI11"
        assert result[0]["data"] == "2025-02-10"


# ---------------------------------------------------------------------------
# get_b3_dividends
# ---------------------------------------------------------------------------


class TestGetB3Dividends:
    def _mock_proventos(self):
        return [
            {"dataPagamento": "2025-01-15", "valorBruto": 0.0850},
            {"dataPagamento": "2025-02-14", "valorBruto": 0.0920},
            {"dataPagamento": "2025-03-14", "valorBruto": 0.0780},
        ]

    def test_returns_dividends_sorted_by_date(self):
        unsorted = [
            {"dataPagamento": "2025-03-14", "valorBruto": 0.078},
            {"dataPagamento": "2025-01-15", "valorBruto": 0.085},
            {"dataPagamento": "2025-02-14", "valorBruto": 0.092},
        ]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = unsorted
            result = get_b3_dividends("MXRF11")

        dates = [r["date"] for r in result]
        assert dates == sorted(dates)

    def test_returns_correct_value_and_source(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = self._mock_proventos()
            result = get_b3_dividends("MXRF11")

        assert result[0]["value"] == pytest.approx(0.085, abs=1e-4)
        assert result[0]["source"] == "b3"

    def test_filters_zero_value_entries(self):
        proventos = [
            {"dataPagamento": "2025-01-15", "valorBruto": 0.0},
            {"dataPagamento": "2025-02-14", "valorBruto": 0.09},
        ]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = proventos
            result = get_b3_dividends("MXRF11")

        assert len(result) == 1
        assert result[0]["value"] == pytest.approx(0.09, abs=1e-4)

    def test_passes_ticker_uppercase_to_b3(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = []
            get_b3_dividends("mxrf11")

        call_kwargs = MockB3.return_value.clearing_creditos_de_proventos.call_args[1]
        assert call_kwargs["filtro_emissor"] == "MXRF11"

    def test_removes_sa_suffix_from_ticker(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = []
            get_b3_dividends("MXRF11.SA")

        call_kwargs = MockB3.return_value.clearing_creditos_de_proventos.call_args[1]
        assert call_kwargs["filtro_emissor"] == "MXRF11"

    def test_uses_default_date_range(self):
        today = datetime.date(2025, 5, 1)
        expected_start = today - datetime.timedelta(days=180)
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = []
            with patch("data.mercados_client.datetime") as mock_dt:
                mock_dt.date.today.return_value = today
                mock_dt.date.side_effect = lambda *a, **kw: datetime.date(*a, **kw)
                mock_dt.timedelta = datetime.timedelta
                get_b3_dividends("MXRF11")

            call_kwargs = MockB3.return_value.clearing_creditos_de_proventos.call_args[1]
            assert call_kwargs["data_inicial"] == expected_start

    def test_uses_valor_key_as_fallback(self):
        proventos = [{"data": "2025-01-10", "valor": 0.07}]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = proventos
            result = get_b3_dividends("HGLG11")

        assert result[0]["value"] == pytest.approx(0.07, abs=1e-4)

    def test_returns_empty_list_on_exception(self):
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.side_effect = RuntimeError("network error")
            result = get_b3_dividends("MXRF11")

        assert result == []

    def test_returns_empty_list_when_mercados_unavailable(self):
        with patch("data.mercados_client.HAS_MERCADOS", False):
            result = get_b3_dividends("MXRF11")

        assert result == []

    def test_date_truncated_to_10_chars(self):
        proventos = [{"dataPagamento": "2025-01-15T00:00:00", "valorBruto": 0.09}]
        with patch("data.mercados_client.B3") as MockB3:
            MockB3.return_value.clearing_creditos_de_proventos.return_value = proventos
            result = get_b3_dividends("MXRF11")

        assert result[0]["date"] == "2025-01-15"
