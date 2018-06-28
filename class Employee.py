class Employee:
 'Common base class for all employees'
 empCount = 0
 def __init__(self, name, salary):
  self.name = name
  self.salary = salary
  Employee.empCount += 1

 def cmath(self):
     print("Total Employee %d" % Employee.empCount)

 def displayEmployee(self):
     print("Name : ", self.name, ", Salary: ", self.salary)
     y=len(self.name)
     print(y)
emp1 = Employee("Zara", 2000)
emp2 = Employee("Manni", 5000)
emp1.cmath()
emp2.displayEmployee()
emp1.cmath()
emp1.displayEmployee()

