from PIL import Image, ImageDraw, ImageFont; import numpy as np
img=Image.open('original.png').convert('RGB'); im=np.array(img).astype(int)
w=(im.min(2)>230)
xs=[-6+31*k for k in range(25)]; ys=[-5]+[26+31*k for k in range(24)]
cells=[]
for j in range(len(ys)-1):
  row=[]
  for i in range(len(xs)-1):
    x0,x1=max(xs[i],0),min(xs[i+1],713); y0,y1=max(ys[j],0),min(ys[j+1],727)
    f=w[y0+2:y1-1,x0+2:x1-1].mean() if x1-x0>4 and y1-y0>4 else 0
    row.append(f>0.15)
  idx=[i for i,v in enumerate(row) if v]
  if idx and j>0:
    for i in range(idx[0],idx[-1]+1): cells.append((j,i))
img=img.resize((img.width*2,img.height*2),Image.LANCZOS); d=ImageDraw.Draw(img)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',17)
for n,(j,i) in enumerate(cells,1):
  x0,x1=max(xs[i],0)*2,min(xs[i+1],713)*2; y0,y1=max(ys[j],0)*2,min(ys[j+1],727)*2
  d.rectangle([x0,y0,x1,y1],outline=(255,0,0),width=2)
  cx,cy=(x0+x1)/2,(y0+y1)/2; t=str(n)
  b=d.textbbox((0,0),t,font=font); tw,th=b[2]-b[0],b[3]-b[1]
  d.rectangle([cx-tw/2-2,cy-th/2-3,cx+tw/2+2,cy+th/2+3],fill=(255,255,200))
  d.text((cx-tw/2,cy-th/2-b[1]),t,fill=(200,0,0),font=font)
img.save('numbered_grid.png'); print(len(cells))
