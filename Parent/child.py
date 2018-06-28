class Parent:
    def __init__(self):
      print ("Calling parent constructor")
    def xyz(self):
        print("kk")
class Child(Parent):
    def __init__(self):
        print ("Calling child constructor")
    def xyz(self):
        print("abc")
c=Child()
c.xyz()
