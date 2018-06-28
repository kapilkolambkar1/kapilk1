x=int(input())
y=(5)
pos=0
neg=0
fra=0

for i in y:
    if i > x:
        pos=pos+1
    if i < x:
        neg=neg+1
    if i in x:
        fra=fra+1
print(pos,)