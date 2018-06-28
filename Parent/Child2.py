class Parent1:
    def __init__(self):
      print ("Calling parent constructor")
    def xyz(self):
        print("kk")
class Parent2:
    def __init__(self):
      print ("Calling parent constructor")
    def xyz(self):
        print("lol")
class Child(Parent1,Parent2):
    def __init__(self):
        print ("Calling child constructor")
c=Child()
c.xyz()
