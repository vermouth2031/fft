import importlib.util,json,struct,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('iq_client',ROOT/'host/iq_client.py');host=importlib.util.module_from_spec(spec);spec.loader.exec_module(host)
class HostTests(unittest.TestCase):
 def test_actual_rtl_records(self):
  seen=0
  for line in (ROOT/'build/vivado/iq_analyzer.sim/sim_1/behav/xsim/core_results.txt').read_text().splitlines():
   parts=line.split();kind='frequency' if parts[0]=='F' else 'burst';w=[int(x,16) for x in parts[2:]]
   result=host.decode_record(struct.pack('<'+'I'*len(w),*w),kind)
   self.assertEqual(result['id'],w[3]);self.assertEqual(result['epoch'],1);seen+=1
   if kind=='frequency' and int(parts[1]) in (2,10):self.assertEqual(result['peak_hz'],-25000000)
  self.assertEqual(seen,78)
 def test_reject_truncated(self):
  with self.assertRaises(ValueError):host.decode_record(b'\x00'*127,'frequency')
 def test_reject_wrong_magic(self):
  with self.assertRaises(ValueError):host.decode_record(b'\x00'*128,'frequency')
 def test_udp_duplicate_and_truncation(self):
  w=[0]*32;w[0]=0x46525131;w[5]=100000000
  packet=struct.pack('<4I',host.MAGIC,0x100,9,1)+struct.pack('<32I',*w)
  class Sock:
   def recv(self,n):return packet
  c=host.Client.__new__(host.Client);c.sock=Sock();c.frequency=[];c.bursts=[];c.packet_sequences=[];c._seen_packets=set();c.active_epoch=None
  c.receive();c.receive();self.assertEqual(len(c.frequency),1)
  packet=packet[:-4]
  with self.assertRaises(ValueError):c.receive()
if __name__=='__main__':unittest.main()
