# python 3 only

import datetime
import sys
import traceback


# extracted from epylib
def FormatExceptionMessage(strng='', shortform=True):
    """
    Format the last occurred exception as a one-line message
    with optional prefix (strng). Return the formatted string.

    Revision history:
    2006-11-24  bug fix in case of shortform not founding "Exception"
    """
    try:
        s = strng + ''.join(traceback.format_exception(
            *sys.exc_info())[-2:]).strip().replace('\n', ': ')
    except:
        s = "ERROR in FormatExceptionMessage!!!!"

    rf = 0
    if shortform:
        rf = s.rfind('Exception:')
        if rf > 0:
            while rf >= 0 and s[rf] != ' ':
                rf -= 1
            rf += 1
        else:
            rf = 0

    return s[rf:]


def GetStartTime(clenins, fullhour=False):
    """
    Return "datetime" when to start (next full minute),
    or optionally when
    full hour is divisable by it (if possible)
    """
    tdelta = datetime.timedelta
    now = datetime.datetime.now()
    dtcm = now.replace(second=0, microsecond=0)

    if now.second > 45:
        dtcm += datetime.timedelta(seconds=60)
    if not fullhour or not clenins:
        return dtcm + tdelta(seconds=60)

    dmn = int(clenins / 60. * 10 + .5)
    if dmn not in [10, 15, 20, 25, 30, 40, 50, 60, 75, 100, 120, 150, 200, 300, 600]:
        dtstart = dtcm + tdelta(seconds=60)
    else:
        dtm = tdelta(0, int(dmn / 10. + .5) * 60)
        dtstart = dtcm - tdelta(seconds=dtcm.minute * 60)
        while dtstart < now + tdelta(seconds=20):
            dtstart += dtm
    return dtstart


def dec2hex(decim):
    """
    Convert decimal to two character upper case hex (for ADAM addressing)
    """
    try:
        dec = int(decim)
        if not 0 <= dec <= 255:
            raise RuntimeError("Invalid ADAM address:%d" % dec)
        hx = hex(dec).upper()[-2:]
        if hx[0] == 'X':
            return "0" + hx[1]
        return hx
    except:
        return None


octhexdict = {0: '000', 1: '001', 2: '010', 3: '011', 4: '100', 5: '101', 6: '110', 7: '111'}


def binfromhex(hexstr):
    """
    Return 8 bit binary representation of value given in hex
    """
    try:
        x = int(hexstr, 16)
        s = ''.join([octhexdict[int(dig)] for dig in oct(x)])
        return ("00000000" + s)[-8:]
    except:
        return None


def dictfromhex(hexstr, length=8):
    """
    Return dict {0:0/1, 1:0/1, ...} of value given in hex.
    """
    try:
        bin = binfromhex(hexstr)  # hex character for status
        dct = {}
        for i in range(0, length):
            dct[i] = int(bin[-i - 1])
        return dct
    except:
        return None


def hex2int(hexs):
    '''
    Convert two's complement hex string (four chars, e.g. 10FF)
    to integer (range -32768 - 32767).
    '''
    try:
        print("Converting:%s" % hexs)
        i = int(hexs, 16)
        if i > 32767:
            i -= 65536
        return i
    except:
        return None


if __name__ == '__main__':
    print("Import me!")
