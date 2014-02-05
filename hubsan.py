from a7105 import *
import time
import logging
import random
import struct

def calc_checksum(packet):
  total = 0
  for char in packet:
    total += struct.unpack('B', char)[0]
  return (256 - (total % 256)) & 0xff

class Hubsan:
  # not sure if byte order is correct
  ID = '\x55\x20\x10\x41'
  CALIBRATION_MAX_CHECKS = 3
  # channels we can use, magic numbers from deviation
  ALLOWED_CHANNELS = [ 0x14, 0x1e, 0x28, 0x32, 0x3c, 0x46, 0x50, 0x5a, 0x64, 0x6e, 0x78, 0x82 ]
  # mystery packet constants
  MYSTERY_CONSTANTS = '\x08\xe4\xea\x9e\x50'
  # mystery ID from deviation
  TX_ID = '\xdb\x04\x26\x79'

  def __init__(self):
    self.a7105 = A7105()

    # generate a random session ID
    self.session_id = struct.pack('BBBB', *(random.randint(0, 255) for n in xrange(4)))
    # choose a random channel
    self.channel, = random.sample(Hubsan.ALLOWED_CHANNELS, 1)

  def init(self):
    self.a7105.init()

    self.init_regs()

    # go into Standby mode
    self.a7105.strobe(State.STANDBY)

    self.calibrate_if()
    self.calibrate_vco(0x00)
    self.calibrate_vco(0xa0)

    # deviation code seems to set up GPIO pins here, looks device-specific
    # we use GPIO1 for 4-wire SPI anyway

    # seems like a reasonable power level
    self.a7105.set_power(Power._30mW)

    # not sure what this is for
    self.a7105.strobe(State.STANDBY)

  def init_regs(self):
    a = self.a7105

    logging.debug('    initializing registers`')
    a.write_id(Hubsan.ID)
    # set various radio options
    a.write_reg(Reg.MODE_CONTROL, 0x63)
    # set packet length (FIFO end pointer) to 0x0f + 1 == 16
    a.write_reg(Reg.FIFO_1, 0x0f)
    # select crystal oscillator and system clock divider of 1/2
    a.write_reg(Reg.CLOCK, 0x05)
    # set data rate division to Fsyck / 32 / 5
    a.write_reg(Reg.DATA_RATE, 0x04)
    # set Fpfd to 32 MHz
    a.write_reg(Reg.TX_II, 0x2b)
    # select BPF bandwidth of 500 KHz and up side band
    a.write_reg(Reg.RX, 0x62)
    # enable manual VGA calibration
    a.write_reg(Reg.RX_GAIN_I, 0x80)
    # set some reserved constants
    a.write_reg(Reg.RX_GAIN_IV, 0x0A)
    # select ID code length of 4, preamble length of 4
    a.write_reg(Reg.CODE_I, 0x07)
    # set demodulator DC estimation average mode,
    # ID code error tolerance = 1 bit, 16 bit preamble pattern detection length
    a.write_reg(Reg.CODE_II, 0x17)
    # set constants
    a.write_reg(Reg.RX_DEM_TEST, 0x47)

  # WTF: these seem to differ from the A7105 spec, this is the deviation version
  def calibrate_if(self):
    logging.debug('    calibrating IF bank')

    # select IF calibration
    self.a7105.write_reg(Reg.CALIBRATION, 0b001)

    # WTF: deviation reads calibration here, not sure why
    calib_n = 0
    # should only take 256 microseconds, but try a few times anyway
    while True:
      if calib_n == 3:
        raise Exception("IF calibration did not complete.")
      elif self.a7105.read_reg(Reg.CALIBRATION) & 0b001 == 0:
        break
      time.sleep(0.001)
      calib_n += 1

    # check calibration succeeded
    if self.a7105.read_reg(Reg.IF_CALIBRATION_I) & 0b1000 != 0:
      raise Exception("IF calibration failed.")
    logging.debug('    calibration complete')

  def calibrate_vco(self, channel):
    logging.debug('    calibrating VCO channel %02x' % (channel))
    # reference code sets 0x24, 0x26 here, deviation skips

    self.a7105.write_reg(Reg.PLL_I, channel)

    # select VCO calibration
    self.a7105.write_reg(Reg.CALIBRATION, 0b010)

    calib_n = 0
    while True:
      if calib_n == 3:
        raise Exception("VCO calibration did not complete.")
      elif self.a7105.read_reg(Reg.CALIBRATION) & 0b010 == 0:
        break
      time.sleep(0.001)
      calib_n += 1

    # check calibration succeeded
    if self.a7105.read_reg(Reg.VCO_CALIBRATION_I) & 0b1000 != 0:
      raise Exception("VCO calibration failed.")
    logging.debug('    calibration complete')


  def build_bind_packet(self, state):
    packet = struct.pack('BB', state, self.channel) + self.session_id + Hubsan.MYSTERY_CONSTANTS + Hubsan.TX_ID
    packet += pbyte(calc_checksum(packet))

    return packet

logging.basicConfig(level = logging.DEBUG)