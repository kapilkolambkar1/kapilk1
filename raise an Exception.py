def submisission(c,d):
    try:
        if c>20 or d>20:
            raise NameError("cf")
    except NameError:
        print("calc cannot above 20")
    else:
        finalvalue=c+d
        return finalvalue
a=input()
b=input()
e=submisission(int(a),int(b))
print(e)