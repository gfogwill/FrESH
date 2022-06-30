# $Id: BaseInstrument.py 1896 2021-12-23 13:27:06Z  $
'''
   Base class for aerosol instruments. Has serial port or socket.
   Subclass this, call super, and implement instrument specific methods for getting data.
   See TSI4000.py  and readTSI4000.py for an implementation example.

   2019/12/31 hs
'''

import os, sys, codecs, serial, datetime, traceback
from time import time, sleep


class BaseInstrument(object) :

    def __init__(self, ini_serial) :
        self.ini = ini_serial
        self.DEBUG = False
        self.LINEEND = '\n'                 # default eol char for writing to files
        self.EOLREAD = '\r'                 # default eol char for reading from serial
        self.EOLWRITE = '\r\n'
        self.previous_timestamp = None      # indicates program start
        self.header = None
        self.timeout = None                 # io timeout
        self.pausetime = None               # pause between consecutive io ops

        self.sp = self._init_serial()
        self.last_data_row = []

    def _init_serial(self) :
        try :
            ini = self.ini
            if 'HOST' in ini :  # use serial via tcp socket (for Moxa or Brainboxes TCP<->serial gateways)
                port = serial.serial_for_url("socket://%s:%s"%(ini["HOST"], ini["PORT"]))

            else :
                port = serial.Serial(ini["PORT"],
                                    baudrate  = ini["BAUDRATE"],
                                    bytesize  = int(ini["BYTES"]),
                                    parity    = getattr(serial,"PARITY_%s"%ini["PARITY"]),
                                    stopbits  = int(ini["STOPBITS"]),
                                    rtscts    = bool(ini.get("RTS", False)),
                                    dsrdtr    = bool(ini.get("DTS", False)),
                                    timeout   = float(ini["TIMEOUT"])
                )
        except :
            print("\nCOULD NOT OPEN PORT!")
            raise

        self.timeout = float(ini['TIMEOUT'])
        if 'PAUSETIME' in ini :
            self.pausetime = float(ini['PAUSETIME'])
        else :
            self.pausetime = 0.3

        if port :
            port.flush()
            port.reset_input_buffer()
            port.reset_output_buffer()

        print("Serial port   : %s" %ini['PORT'])
        print("Baudrate      : %s" %ini['BAUDRATE'])
        print("Timeout       : %f" %self.timeout)
        print("Pausetime     : %f" %self.pausetime)

        return port


    def read_all_available_as_bytearr(self):
        '''
        Return all bytes read from serial port
        '''
        data = bytearray()
        while (self.sp.in_waiting>0) :
            data += (self.sp.read(self.sp.in_waiting))
            sleep(TIMEOUT/5.0)

        return data


    def read_all_available(self) :
        '''
        Read all available data, return string
        '''
        data = ''
        while (self.sp.in_waiting>0) :
            data += (self.sp.read(self.sp.in_waiting)).decode('latin-1')
            sleep(self.pausetime)

        return data


    def read_linedata(self) :
        '''
        Read one line of data terminated by EOLREAD, return array
        '''
        eol = self.EOLREAD
        line = []
        while True :
            for c in self.sp.read() :
                cchar = chr(c)
                line.append(cchar.strip())
                if cchar == eol :
                    return line


    def send_command(self, command, pausetime=-1, usereadline=False, bytemode=False) :
        '''
        Send command to serial port, read reply. Return stripped string.
        '''
        data = self.LINEEND
        if pausetime<0 : pausetime = self.pausetime
        
        if self.DEBUG : print("Sending %s"%command)
        if not bytemode :    
            self.sp.write( ('%s%s'%(command, self.EOLWRITE)).encode('latin-1') )
        else :
            self.sp.write(bytes(command+self.EOLWRITE, 'latin1'))
        self.sp.flush()
        sleep(pausetime)

        if usereadline :
            data = ''.join(self.read_linedata())
        else :
            while (self.sp.inWaiting()>0) :
                try :
                    data += (self.sp.read(self.sp.inWaiting())).decode('latin-1')
                    sleep(pausetime/2.0)
                except :
                    if self.DEBUG :
                        print("DEBUG: BARFED - %s"%traceback.print_exc())

        if self.DEBUG : print(data) ;
        return data.strip()


    def init_instrument(self) :
        raise BaseException("Implement me in actual subclass")


    def get_model(self) :
        raise BaseException("Implement me in actual subclass")


    def set_meas_params(self) :
        raise BaseException("Implement me in actual subclass")


    def setup_instrument(self) :
        self.init_instrument()
        self.get_model()
        self.set_meas_params()


    # main method for retrieving data
    # should return raw data and update the internal last_data_row array
    def get_data(self) :
        raise BaseException("Implement me in actual subclass")


    def shutdown(self) :
        if self.sp :
            self.sp.flush()
        self.sp.close()



if __name__ == "__main__" :
    print("I'm not executable, import me!")
