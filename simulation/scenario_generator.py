import os
from loguru import logger

class ScenarioGenerator:
    """
    Generates dynamic .rou.xml files for different traffic scenarios.
    Assumes .net.xml already exists in simulation/sumo_config.
    """
    def __init__(self, output_dir: str = "simulation/sumo_config"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _write_routes(self, filename: str, vehicle_count: int, period: float):
        filepath = os.path.join(self.output_dir, filename)
        
        # Extremely simplified route generation for a 4-way intersection
        # N->S, S->N, E->W, W->E
        xml_content = f"""<routes>
    <vType id="car" accel="0.8" decel="4.5" sigma="0.5" length="5" minGap="2.5" maxSpeed="16.67" guiShape="passenger"/>
    <route id="r_N_S" edges="N_in S_out"/>
    <route id="r_S_N" edges="S_in N_out"/>
    <route id="r_E_W" edges="E_in W_out"/>
    <route id="r_W_E" edges="W_in E_out"/>
    
    <flow id="flow_N_S" type="car" route="r_N_S" begin="0" end="{vehicle_count*period}" period="{period}" />
    <flow id="flow_S_N" type="car" route="r_S_N" begin="0" end="{vehicle_count*period}" period="{period}" />
    <flow id="flow_E_W" type="car" route="r_E_W" begin="0" end="{vehicle_count*period}" period="{period}" />
    <flow id="flow_W_E" type="car" route="r_W_E" begin="0" end="{vehicle_count*period}" period="{period}" />
</routes>
"""
        with open(filepath, "w") as f:
            f.write(xml_content)
        logger.info(f"Generated route file: {filepath}")

    def generate(self, scenario_type: str):
        if scenario_type == "normal":
            self._write_routes("routes.rou.xml", vehicle_count=1000, period=2.0)
        elif scenario_type == "rush_hour":
            self._write_routes("routes.rou.xml", vehicle_count=3000, period=0.5)
        elif scenario_type == "accident":
            # In a real impl, we'd inject stopped vehicles via TraCI or specific route definitions
            self._write_routes("routes.rou.xml", vehicle_count=1000, period=2.0)
            logger.warning("Accident scenario requested. Vehicles will be artificially stopped via TraCI during runtime.")
        else:
            logger.error(f"Unknown scenario: {scenario_type}")
            
    def write_sumocfg(self, net_file: str = "network.net.xml", route_file: str = "routes.rou.xml"):
        filepath = os.path.join(self.output_dir, "network.sumocfg")
        xml_content = f"""<configuration>
    <input>
        <net-file value="{net_file}"/>
        <route-files value="{route_file}"/>
    </input>
    <time>
        <begin value="0"/>
    </time>
</configuration>
"""
        with open(filepath, "w") as f:
            f.write(xml_content)
        logger.info(f"Generated SUMO config: {filepath}")
