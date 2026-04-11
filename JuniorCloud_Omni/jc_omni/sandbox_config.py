class SandboxConfig:
    def __init__(self, branch="A"):
        self.branch = branch
        self.reset_to_defaults()

    def reset_to_defaults(self):
        if self.branch == "A":
            self.q_threshold, self.z_buy, self.z_sell = 0.90, -1.5, 1.5
        elif self.branch == "B":
            self.q_threshold, self.z_buy, self.z_sell = 0.75, -1.0, 1.2
        elif self.branch == "C":
            self.q_threshold, self.z_buy, self.z_sell = 0.98, -2.5, 2.5

    def update(self, params):
        self.q_threshold = float(params.get('q', self.q_threshold))
        self.z_buy = float(params.get('zb', self.z_buy))
        self.z_sell = float(params.get('zs', self.z_sell))
