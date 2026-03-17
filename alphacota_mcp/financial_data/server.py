"""
AlphaCota Financial Data MCP Server

MCP server que expoe os motores quantitativos do AlphaCota como tools
para qualquer AI (Claude, Cursor, Cline, etc).

Tools disponiveis:
  Market:     get_fii_price, get_fii_detail, get_scanner
  Macro:      get_macro_snapshot
  Screening:  find_undervalued_fiis, find_high_dividend_fiis, scan_opportunities
  Analysis:   run_correlation, run_momentum, run_stress, run_clusters
  News:       get_fii_news, get_market_news
  AI:         analyze_fii_sentiment, generate_fii_report

Uso:
  python -m alphacota_mcp.financial_data.server
  Ou via config MCP: {"command": "python", "args": ["-m", "alphacota_mcp.financial_data.server"]}
"""

import sys
from pathlib import Path

# Add project root to path so we can import core/, data/, services/
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP

# Create the MCP server
mcp = FastMCP(
    "alphacota-financial-data",
    version="1.0.0",
)

# Register all tools from submodules
from alphacota_mcp.financial_data.tools.market import register_market_tools
from alphacota_mcp.financial_data.tools.macro import register_macro_tools
from alphacota_mcp.financial_data.tools.screening import register_screening_tools
from alphacota_mcp.financial_data.tools.analysis import register_analysis_tools
from alphacota_mcp.financial_data.tools.news_tools import register_news_tools
from alphacota_mcp.financial_data.tools.ai_tools import register_ai_tools

register_market_tools(mcp)
register_macro_tools(mcp)
register_screening_tools(mcp)
register_analysis_tools(mcp)
register_news_tools(mcp)
register_ai_tools(mcp)


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
