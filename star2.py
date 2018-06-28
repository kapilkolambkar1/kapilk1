x=int(input())
for i in range(x):
    for j in range (i,i+1):
     print(" "*(x-j-1),end=)
     print("*"*(j+1))