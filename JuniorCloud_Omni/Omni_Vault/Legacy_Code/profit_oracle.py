class ProfitOracle:
    def __init__(self):
        self.long_term_days = 365

    def generate_full_inference(self, current_price, cost_basis, days_held, z_score, math_status):
        ms = math_status
        projections = ms.get('projections', {})
        short_v = ms.get('velocity', 0)
        accel = ms.get('acceleration', 0)
        
        # Redundancy Check: Math Engine Status
        if short_v == 0 and accel == 0:
            return {
                "short_term_inference": "GHOSTING",
                "macro_trend_inference": "INSUFFICIENT DATA",
                "tax_strategy_call": "ENGINE_OFFLINE"
            }
        
        # Multi-Horizon Retrieval
        v7 = projections.get('7d', {}).get('velocity', 0)
        v30 = projections.get('30d', {}).get('velocity', 0)

        # 1. Short Term Kinematics (Based on live acceleration)
        if short_v > 0 and accel > 0: short_trend = "Aggressive Bullish"
        elif short_v > 0 and accel <= 0: short_trend = "Exhausted Bullish"
        elif short_v < 0 and accel < 0: short_trend = "Aggressive Bearish"
        else: short_trend = "Exhausted Bearish"

        # 2. Deep Time Projections
        cycle = "Macro Expansion" if short_v > 0 and v30 > 0 else "Macro Contraction" if short_v < 0 and v30 < 0 else "Transition Phase"
        outlook = f"7d: {'Bull' if v7 > 0 else 'Bear'} | 30d: {'Bull' if v30 > 0 else 'Bear'} | {cycle}"

        # 3. Consensus Logic (Requiring 2+ positives to agree)
        tax_call = "WATCHING"
        if cost_basis == 0:
            # Consensus: Deep Value requires negative Z AND positive acceleration AND positive 7d velocity
            if z_score < -2.0 and accel > 0 and v7 > 0: 
                tax_call = "ACCUMULATE (Deep Value Consensus)"
            elif z_score > 2.0 and accel < 0: 
                tax_call = "AVOID (Overbought Breakdown)"
        else:
            pnl_raw = current_price - cost_basis
            if pnl_raw < 0 and accel < 0:
                tax_call = f"TAX-LOSS HARVEST (-${abs(pnl_raw):.2f})"
            elif pnl_raw > 0 and accel < 0 and z_score > 1.5:
                tax_call = f"TAKE PROFITS (+${pnl_raw:.2f})"

        return {
            "short_term_inference": short_trend,
            "macro_trend_inference": outlook,
            "tax_strategy_call": tax_call
        }