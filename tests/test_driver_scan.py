import unittest
from driver_scan import classify,parse_drivers
class DriverTests(unittest.TestCase):
 def test_categories(self):
  self.assertEqual(classify('Intel Wireless Bluetooth'),'Bluetooth')
  self.assertEqual(classify('NVIDIA GeForce Graphics'),'Graphics')
 def test_single_json(self):
  d=parse_drivers('{"DeviceID":"abc","DeviceName":"Intel Wireless Bluetooth","DriverVersion":"1.2","DriverProviderName":"Intel"}')
  self.assertEqual(len(d),1)
  self.assertEqual(d[0]['version'],'1.2')
 def test_duplicate(self):
  a='{"DeviceID":"abc","DeviceName":"Intel Wireless Bluetooth","DriverVersion":"1.2"}'
  self.assertEqual(len(parse_drivers('['+a+','+a+']')),1)