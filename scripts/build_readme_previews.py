# /web3node/scripts/build_readme_previews.py

import os
import json

def generate_sim_data():
    """Generates a static SVD-based dataset for UI hydration."""
    # Simulated Gamma Signal Inference data
    return {
        "timestamp": "2026-04-10T05:15:00Z",
        "market_sentiment": 0.82,
        "gamma_levels": [1.2, 1.5, 1.8, 2.1],
        "manifold_projection": [[0.1, 0.2], [0.3, 0.4]],
        "status": "SIMULATED_PREVIEW"
    }

def pack_flex_dashboard(input_html, output_path):
    """Injects sim data into the HTML and disables live WebSockets."""
    with open(input_html, 'r') as f:
        content = f.read()

    sim_data = json.dumps(generate_sim_data())
    
    # Logic Gate: Inject the simulation script before the closing body tag
    injection = f"""
    <script>
        window.JC_PREVIEW_MODE = true;
        window.JC_SIM_DATA = {sim_data};
        console.log("Orchestrator: Dashboard hydrated with static SVD manifold.");
        // Disable live WebSocket attempts in preview mode
        if (window.AuditAPI) window.AuditAPI.connect = () => {{}};
    </script>
    """
    
    flex_content = content.replace("</body>", f"{injection}</body>")
    
    with open(output_path, 'w') as f:
        f.write(flex_content)
    print(f"Flex Artifact Deployed: {output_path}")

if __name__ == "__main__":
    # Source paths from JC-SDK-CORE mapping
    src = "../web3node/dashboard.html"
    dest = "../web3node/dist/preview_dashboard.html"
    
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(src):
        pack_flex_dashboard(src, dest)