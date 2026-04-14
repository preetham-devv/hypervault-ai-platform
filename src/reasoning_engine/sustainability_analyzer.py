"""
Sustainability Analyzer — domain-specific reasoning for ESG metrics
using AlloyDB data + Gemini Flash.
"""

from src.reasoning_engine.gemini_client import GeminiClient


class SustainabilityAnalyzer:
    SYSTEM_PROMPT = (
        "You are an ESG and sustainability expert. Analyze environmental "
        "and operational data. Provide actionable recommendations for "
        "reducing carbon footprint and improving resource efficiency."
    )

    def __init__(self):
        self.gemini = GeminiClient()

    def analyze_carbon_footprint(self, data: list[dict]) -> str:
        context = "\n".join(
            f"- {r.get('department','N/A')}: {r.get('carbon_kg',0)} kg CO2, "
            f"{r.get('energy_kwh',0)} kWh, {r.get('waste_kg',0)} kg waste"
            for r in data
        )
        prompt = f"""## Carbon Footprint Data
{context}

Provide: 1) Highest impact departments 2) Reduction targets
3) Quick wins vs long-term strategies 4) Estimated cost savings"""

        return self.gemini.generate(
            prompt=prompt, system_instruction=self.SYSTEM_PROMPT, temperature=0.2
        )

    def generate_esg_report_section(self, metrics: dict) -> str:
        prompt = f"""Generate ESG report section:
- Emissions: {metrics.get('total_emissions_tons','N/A')} tons CO2e
- YoY change: {metrics.get('yoy_change_pct','N/A')}%
- Renewable share: {metrics.get('renewable_pct','N/A')}%
- Water: {metrics.get('water_cubic_m','N/A')} m³
- Waste diversion: {metrics.get('waste_diversion_pct','N/A')}%

Write 2-3 paragraphs for an annual sustainability report."""

        return self.gemini.generate(
            prompt=prompt, system_instruction=self.SYSTEM_PROMPT, temperature=0.4
        )
