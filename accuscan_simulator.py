# accuscan_sim.py
import random
import time

class AccuScanSimulator:
    """
    Klasa symulująca skaner AccuScan.
    Generuje losowe (lub prawie losowe) wartości D1, D2, lumps, necks etc.
    Możesz rozbudować o kolejne parametry.
    """
    def __init__(self,
                 d1_mean=18.0, d1_std=0.05,
                 d2_mean=18.0, d2_std=0.05,
                 d3_mean=18.0, d3_std=0.05,
                 d4_mean=18.0, d4_std=0.05,
                 lumps_chance=0.01,
                 necks_chance=0.01):
        """
        :param d1_mean: średnia wartość D1 (mm)
        :param d1_std: odchylenie standardowe dla losowania D1
        :param lumps_chance: prawdopodobieństwo wystąpienia lumps (np. 0.01 = 1%)
        :param necks_chance: prawdopodobieństwo wystąpienia necks
        """
        self.d1_mean = d1_mean
        self.d1_std = d1_std
        self.d2_mean = d2_mean
        self.d2_std = d2_std
        self.d3_mean = d3_mean
        self.d3_std = d3_std
        self.d4_mean = d4_mean
        self.d4_std = d4_std
        self.lumps_chance = lumps_chance
        self.necks_chance = necks_chance

    def read_data(self) -> dict:
        """
        Zwraca słownik z danymi podobnymi do read_accuscan_data().
        """
        d1 = random.gauss(self.d1_mean, self.d1_std)  # Gauss(średnia, std)
        d2 = random.gauss(self.d2_mean, self.d2_std)
        d3 = random.gauss(self.d3_mean, self.d3_std)
        d4 = random.gauss(self.d4_mean, self.d4_std)

        lumps = 1 if random.random() < self.lumps_chance else 0
        necks = 1 if random.random() < self.necks_chance else 0

        # Ewentualnie można generować D3, D4, alarmy itp.
        return {
            "status_byte": 0,
            "D1": d1,
            "D2": d2,
            "D3": d3,
            "D4": d4,
            "lumps": lumps,
            "necks": necks,
            "zl_zero_lump_alarm": False,
            "zn_zero_neck_alarm": False,
            "num_scans": 10,
            "flaw_preset_diameter": 18.0,
            "lump_threshold": 0.3,
            "neck_threshold": 0.3,
            "flaw_mode_word": 0,
            "upper_tolerance": 0.5,
            "under_tolerance": 0.5
        }
