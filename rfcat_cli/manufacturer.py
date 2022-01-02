import logging
import time


from rflib import *

class SettingsObject:

  def _parse_settings(self, cfg, setting_list):
    for setting in setting_list:
      if setting in cfg:
        self.__dict__[setting] = cfg[setting]

class RadioSettings(SettingsObject):

  def __init__(self, cfg):
    self.freq = 433920000
    self.deviation = 5200

    if cfg is not None:
      self._parse_cfg(cfg)

  def _parse_cfg(self, cfg):
    self._parse_settings(cfg, [
      "freq",
      "deviation"
    ])

  def setup(self, d: RfCat):
    d.setFreq(self.freq)
    d.setMdmDeviatn(self.deviation)

class ModemSettings(SettingsObject):
  @classmethod
  def lookup_modulation(cls, mod_str: str):
    ModulationMap = {
      "FSK": MOD_2FSK,
      "2FSK": MOD_2FSK,
      "GFSK": MOD_GFSK,
      "OOK": MOD_ASK_OOK,
      "ASK": MOD_ASK_OOK,
      "MSK": MOD_MSK
    }
    if mod_str in ModulationMap:
      return ModulationMap[mod_str]
    else:
      raise KeyError(f"Unknown modulation scheme '{mod_str}'")

  @classmethod
  def lookup_preample(cls, count: int):
    if count > 16:
      return MFMCFG1_NUM_PREAMBLE_24
    elif count > 12:
      return MFMCFG1_NUM_PREAMBLE_16
    elif count > 8:
      return MFMCFG1_NUM_PREAMBLE_12
    elif count > 6:
      return MFMCFG1_NUM_PREAMBLE_8   
    elif count > 4:
      return MFMCFG1_NUM_PREAMBLE_6   
    elif count > 3:
      return MFMCFG1_NUM_PREAMBLE_4   
    elif count > 2:
      return MFMCFG1_NUM_PREAMBLE_3
    else:
      return MFMCFG1_NUM_PREAMBLE_2

  def __init__(self, cfg):
    self.modulation = MOD_GFSK
    self.channel_bw = 63000
    self.data_rate = 4880
    self.num_preamble = ModemSettings.lookup_preample(24)
    self.sync_word = 0x1693
    self.manchester = True
    self.fec = False
    self.whitening = False
    self.pkt_len = 13

    if cfg is not None:
      self._parse_cfg(cfg)

  def _parse_cfg(self, cfg):
    if 'modulation' in cfg:
      self.modulation = ModemSettings.lookup_modulation(cfg['modulation'])
    if 'num_preamble' in cfg:
      self.num_preamble = ModemSettings.lookup_preample(cfg['num_preamble'])

    self._parse_settings(cfg, [
      "channel_bw",
      "data_rate",
      "sync_word",
      "manchester",
      "fec",
      "whitening",
      "pkt_len",
    ])
    

  def setup(self, d: RfCat):
    d.setMdmModulation(self.modulation)
    d.setMdmChanBW(self.channel_bw)
    d.setMdmDRate(self.data_rate)
    d.setMdmNumPreamble(preamble=self.num_preamble)
    
    if self.pkt_len > 0:
      d.makePktFLEN(self.pkt_len)
    else:
      d.makePktVLEN()

    d.setMdmSyncWord(self.sync_word)

    d.setEnablePktDataWhitening(enable=self.whitening)
    d.setEnableMdmManchester(enable=self.manchester)
    d.setEnableMdmFEC(enable=self.fec)


class Command:

  def __init__(self, cfg: dict):
    self.name = cfg['name']
    if 'desc' in cfg:
      self.desc = cfg['desc']
    else:
      self.desc = cfg['name']

    self.code = bytearray(cfg['code'], encoding='latin-1')
    
class RepeatSettings(SettingsObject):

  def __init__(self, cfg: dict):
    self.count = 3
    self.delay = 100
    self.radio_on = False

class Manufacturer:

  def __init__(self, cfg: dict):
    self.radio = RadioSettings(cfg['radio'] if 'radio' in cfg else None)
    self.modem = ModemSettings(cfg['modem'] if 'modem' in cfg else None)
    self.repeat = RepeatSettings(cfg['repeat'] if 'repeat' in cfg else None)

    self.commands = {}
    self._parse_commands(cfg['commands'] if 'commands' in cfg else None)

  def _parse_commands(self, cfg_cmds):
    if cfg_cmds is None:
      return

    for cfg_cmd in cfg_cmds:
      cmd = (Command(cfg_cmd))
      self.commands[cfg_cmd['name']] = cmd
    
  def setup(self, d: RfCat):
    self.radio.setup(d)
    self.modem.setup(d)

    #logging.debug(d.reprRadioConfig())

  def tx_cmd(self, d: RfCat, name: str):
    cmd = self.commands[name]

    for t in range(self.repeat.count):
      logging.debug(f'Sending {cmd.code}')
      d.RFxmit(cmd.code)
      if t < self.repeat.count-1:
        logging.debug(f'Waiting for {self.repeat.delay}ms')
        time.sleep(self.repeat.delay*0.001)