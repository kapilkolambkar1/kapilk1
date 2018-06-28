try:
   open("C:/Users/Kapil k/PycharmProjects/kapilk/japan", "w")as fo
   fo.write( "Python is a great language.\nYeah its great!!\n");
   fo.close()
except PermissionError:
   print("dont have Permission")
