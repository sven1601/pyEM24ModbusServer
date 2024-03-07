import configparser
import os
import logging
import sys
import threading
import time
import requests
from pyModbusTCP.server import ModbusServer, DataBank

class MeterData:
    def __init__(self,
                 l1_volt, l2_volt, l3_volt,
                 l1_current, l2_current, l3_current,
                 l1_power, l2_power, l3_power,
                 l1_energy, l2_energy, l3_energy,
                 l1_energy_ret, l2_energy_ret, l3_energy_ret,
                 energy_total, energy_total_ret, power_total):
        self.l1_volt = l1_volt
        self.l2_volt = l2_volt
        self.l3_volt = l3_volt
        self.l1_current = l1_current
        self.l2_current = l2_current
        self.l3_current = l3_current
        self.l1_power = l1_power
        self.l2_power = l2_power
        self.l3_power = l3_power
        self.l1_energy = l1_energy
        self.l2_energy = l2_energy
        self.l3_energy = l3_energy
        self.l1_energy_ret = l1_energy_ret
        self.l2_energy_ret = l2_energy_ret
        self.l3_energy_ret = l3_energy_ret
        self.energy_total = energy_total
        self.energy_total_ret = energy_total_ret
        self.power_total = power_total


meterValues = MeterData.__new__(MeterData)


def getLogLevel():
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    logLevelString = config['DEFAULT']['LogLevel']
    if logLevelString:
        level = logging.getLevelName(logLevelString)
    else:
        level = logging.INFO
    return level


def _getConfig():
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    return config


def _getShellyStatusUrl():
    config = _getConfig()
    url = "http://%s:%s@%s/status" % (
        config['SHELLY']['Username'], config['SHELLY']['Password'], config['SHELLY']['Host'])
    url = url.replace(":@", "")
    return url


def _getShellyData() -> MeterData:
    url = _getShellyStatusUrl()
    meter_r = requests.get(url=url, timeout=5)

    # check for response
    if not meter_r:
        raise ConnectionError("No response from Shelly 3EM - %s" % url)

    meter_data = meter_r.json()

    # check for Json
    if not meter_data:
        raise ValueError("Converting response to JSON failed")

    return meter_data

def meter_read_thread():
    global meterValues
    while True:
        try:
            meter_data = _getShellyData()
            values = MeterData(
                l1_volt=meter_data['emeters'][0]['voltage'],
                l2_volt=meter_data['emeters'][1]['voltage'],
                l3_volt=meter_data['emeters'][2]['voltage'],
                l1_current=meter_data['emeters'][0]['current'],
                l2_current=meter_data['emeters'][1]['current'],
                l3_current=meter_data['emeters'][2]['current'],
                l1_power=meter_data['emeters'][0]['power'],
                l2_power=meter_data['emeters'][1]['power'],
                l3_power=meter_data['emeters'][2]['power'],
                l1_energy=meter_data['emeters'][0]['total'],
                l2_energy=meter_data['emeters'][1]['total'],
                l3_energy=meter_data['emeters'][2]['total'],
                l1_energy_ret=meter_data['emeters'][0]['total_returned'],
                l2_energy_ret=meter_data['emeters'][1]['total_returned'],
                l3_energy_ret=meter_data['emeters'][2]['total_returned'],
                energy_total=meter_data['emeters'][0]['total'] +
                             meter_data['emeters'][1]['total'] +
                             meter_data['emeters'][2]['total'],
                energy_total_ret=meter_data['emeters'][0]['total_returned'] +
                                 meter_data['emeters'][1]['total_returned'] +
                                 meter_data['emeters'][2]['total_returned'],
                power_total=meter_data['total_power']
                )

            meterValues = values

        except Exception as e:
            logging.error("Exception: " + str(e))

        time.sleep(5)


class Regs(DataBank):

    def __init__(self):
        # turn off allocation of memory for standard modbus object types
        # only "holding registers" space will be replaced by dynamic build values.
        super().__init__(virtual_mode=True)

    def get_holding_registers(self, address, number=1, srv_info=None):
        global meterValues

        #logging.info("Reg: " + hex(address) + "; Count: " + str(number))

        if number > 1000:
            return

        if address == 0x0B:
            return [0x670]  # Model 1648 -> EM24DINAV23XE1X
        if address == 0x0302:
            return [8 * 256 + 1 * 256 + 1]  # Version / Revision Measurement Module
        if address == 0x0304:
            return [8 * 256 + 6 * 256 + 1]  # Version / Revision Communication Module
        if address == 0x1002:
            return [0x00]  # System 3P.n
        if address == 0x5000:
            return [ord('B') * 256 + ord('V'), ord('0') * 256 + ord('4'), ord('2') * 256 + ord('0'),
                    ord('0') * 256 + ord('3'), ord('1') * 256 + ord('0'), ord('0') * 256 + ord('1'),
                    ord('1') * 256]  # SN-> BK0390085001X
        if address == 0xA000:
            return [0x07]  # Type of application

        if 0 <= address <= 0xA100 and 0 < number < 80:

            # Create return object with EM24 protocol
            dataArray = [
                (int(round(meterValues.l1_volt * 10, 0)) & 0x0000FFFF), (int(meterValues.l1_volt * 10) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l2_volt * 10, 0)) & 0x0000FFFF), (int(meterValues.l2_volt * 10) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l3_volt * 10, 0)) & 0x0000FFFF), (int(meterValues.l3_volt * 10) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0, 0,
                (int(meterValues.l1_current * 1000) & 0x0000FFFF), (int(meterValues.l1_current * 1000) & 0xFFFF0000) >> 16,
                (int(meterValues.l2_current * 1000) & 0x0000FFFF), (int(meterValues.l2_current * 1000) & 0xFFFF0000) >> 16,
                (int(meterValues.l3_current * 1000) & 0x0000FFFF), (int(meterValues.l3_current * 1000) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l1_power * 10, 0)) & 0x0000FFFF), (int(round(meterValues.l1_power * 10, 0)) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l2_power * 10, 0)) & 0x0000FFFF), (int(round(meterValues.l2_power * 10, 0)) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l3_power * 10, 0)) & 0x0000FFFF), (int(round(meterValues.l3_power * 10, 0)) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                (int(round(meterValues.power_total * 10, 0)) & 0x0000FFFF), (int(round(meterValues.power_total * 10, 0)) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0,
                0,
                0,
                0,
                0,
                0,
                (int(round(meterValues.energy_total / 1000 * 10, 1)) & 0x0000FFFF), (int(round(meterValues.energy_total / 1000 * 10, 1)) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                (int(round(meterValues.l1_energy / 1000 * 10, 1)) & 0x0000FFFF), (int(round(meterValues.l1_energy / 1000 * 10, 1)) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l2_energy / 1000 * 10, 1)) & 0x0000FFFF), (int(round(meterValues.l2_energy / 1000 * 10, 1)) & 0xFFFF0000) >> 16,
                (int(round(meterValues.l3_energy / 1000 * 10, 1)) & 0x0000FFFF), (int(round(meterValues.l3_energy / 1000 * 10, 1)) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                (int(round(meterValues.energy_total_ret / 1000 * 10, 1)) & 0x0000FFFF), (int(round(meterValues.energy_total_ret / 1000 * 10, 1)) & 0xFFFF0000) >> 16,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0,
                0, 0
            ]

            # Return only requested data
            return dataArray[address:address+number]


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        level=getLogLevel(),
                        handlers=[
                            logging.FileHandler("%s/current.log" % (os.path.dirname(os.path.realpath(__file__)))),
                            logging.StreamHandler()
                        ])

    logging.info("Main Start")

    meter_thread = threading.Thread(target=meter_read_thread)
    meter_thread.start()

    # init modbus server and start it
    server = ModbusServer(host='0.0.0.0', port=1502, data_bank=Regs(), no_block=True)
    print (server)
    try:
        server.start()
    except Exception as e:
        logging.error("Server start exception: " + str(e))

    while(True):

        if not meter_thread.is_alive():
            logging.error("Thread error")
            sys.exit(-1)

        #logging.info("Thread is running")
        time.sleep(10)

