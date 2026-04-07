"""Entry point: python -m alphacota_mcp.financial_data"""

from alphacota_mcp.financial_data.server import mcp

if __name__ == "__main__":
    mcp.run()
