import os
import sys
from loguru import logger
from config.settings import settings

# Must be declared before importing traci
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    logger.warning("Please declare environment variable 'SUMO_HOME'")

import traci

class SumoBridge:
    """
    Manages TraCI connection to SUMO.
    """
    def __init__(self, sumo_cfg_path: str, use_gui: bool = False):
        self.sumo_cfg_path = sumo_cfg_path
        self.use_gui = use_gui or settings.SUMO_GUI
        self.binary = "sumo-gui" if self.use_gui else "sumo"

    def start(self):
        cmd = [self.binary, "-c", self.sumo_cfg_path, "--step-length", "1.0", "--no-warnings", "true"]
        logger.info(f"Starting SUMO with command: {' '.join(cmd)}")
        traci.start(cmd)

    def step(self):
        traci.simulationStep()

    def get_queue_length(self, edge_id: str) -> int:
        return traci.edge.getLastStepHaltingNumber(edge_id)

    def get_avg_wait_time(self, edge_id: str) -> float:
        return traci.edge.getWaitingTime(edge_id)

    def set_phase(self, tls_id: str, phase_index: int):
        traci.trafficlight.setPhase(tls_id, phase_index)
        
    def close(self):
        traci.close()
        logger.info("SUMO connection closed.")

if __name__ == "__main__":
    # Test script
    bridge = SumoBridge("simulation/sumo_config/network.sumocfg", use_gui=True)
    try:
        bridge.start()
        for i in range(100):
            bridge.step()
    except Exception as e:
        logger.error(f"SUMO error: {e}")
    finally:
        bridge.close()
