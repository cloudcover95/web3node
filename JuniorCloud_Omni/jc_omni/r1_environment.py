# jc_omni/rl_environment.py
import gymnasium as gym
from gymnasium import spaces
import numpy as np
import pandas as pd
from scipy.linalg import svd
import warnings

warnings.filterwarnings("ignore")

class OmniSovereignEnv(gym.Env):
    """
    JuniorCloud Custom RL Environment.
    Observation Space: Z-Score, Velocity, Acceleration, BitNet SVD Signatures, Balance, Holdings.
    Action Space: 0 (Harvest), 1 (Watch), 2 (Accumulate)
    """
    def __init__(self, df_history: pd.DataFrame, initial_balance=10000):
        super(OmniSovereignEnv, self).__init__()
        self.df = df_history.reset_index(drop=True)
        self.initial_balance = initial_balance
        
        # Actions: 0=Sell, 1=Hold, 2=Buy
        self.action_space = spaces.Discrete(3)
        
        # 8 Data Points for the Neural Net to watch
        self.obs_shape = 8
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(self.obs_shape,), dtype=np.float32)
        
        self.current_step = 0
        self.balance = self.initial_balance
        self.holdings = 0
        self.net_worth = self.initial_balance

    def _get_bitnet_svd(self, window_data):
        if len(window_data) < 5: return [0.0, 0.0, 0.0]
        try:
            matrix = np.array(window_data).reshape(-1, 1)
            U, _, _ = svd(matrix, full_matrices=False)
            # 1-Bit Quantization (-1, 0, 1)
            bit_sig = np.sign(U[:, 0]).tolist()
            # Pad or truncate to 3 core structural components
            while len(bit_sig) < 3: bit_sig.append(0.0)
            return [float(bit_sig[0]), float(bit_sig[1]), float(bit_sig[2])]
        except: return [0.0, 0.0, 0.0]

    def _get_observation(self):
        row = self.df.iloc[self.current_step]
        start_idx = max(0, self.current_step - 10)
        svd_comp = self._get_bitnet_svd(self.df['price'].iloc[start_idx:self.current_step].values)
        
        obs = np.array([
            row.get('Robust_Z', 0.0),
            row.get('velocity', 0.0),
            row.get('acceleration', 0.0),
            svd_comp[0], svd_comp[1], svd_comp[2],
            self.balance / self.initial_balance, 
            self.holdings
        ], dtype=np.float32)
        return obs

    def step(self, action):
        current_price = self.df.iloc[self.current_step]['price']
        prev_net_worth = self.net_worth
        
        # Engine Physics Execution
        if action == 2 and self.balance >= current_price:
            self.holdings += 1
            self.balance -= current_price
        elif action == 0 and self.holdings > 0:
            self.balance += current_price
            self.holdings -= 1

        self.current_step += 1
        self.net_worth = self.balance + (self.holdings * current_price)
        
        reward = self.net_worth - prev_net_worth
        done = self.current_step >= len(self.df) - 1
        
        return self._get_observation(), reward, done, False, {}

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        self.balance = self.initial_balance
        self.holdings = 0
        self.net_worth = self.initial_balance
        return self._get_observation(), {}