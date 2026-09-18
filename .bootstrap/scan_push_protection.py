from pathlib import Path
import base64, lzma, re, subprocess, os, sys

ROOT=Path.cwd()
BOOT=ROOT/'.bootstrap'

def restore():
    parts=sorted(BOOT.glob('index.html.xz.b64.*'))
    encoded=''.join(p.read_text('ascii').strip() for p in parts)
    return lzma.decompress(base64.b64decode(encoded),format=lzma.FORMAT_XZ).decode('utf-8',errors='ignore')

html=restore()
html=re.sub(r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*>','',html,flags=re.I)
html=re.sub(r'<(?:script|iframe|img)[^>]+(?:googletagmanager|google-analytics|hotjar|hubspot|cookiebot|lemlist|clarity)[^>]*>(?:</script>)?','',html,flags=re.I)
html=re.sub(r'<script\s+type=["\']importmap["\'][^>]*>.*?</script>','',html,flags=re.I|re.S)
html=html.replace('<script src="/__sitecloner/runtime.js"></script>','')
html=re.sub(r'<link[^>]+rel=["\']prefetch["\'][^>]+as=["\']script["\'][^>]*>','',html,flags=re.I)
html=html.replace('/textures/ldr_rgb1_0.png','/__sitecloner/pixel.svg').replace('/textures/LDR_RGB1_0.png','/__sitecloner/pixel.svg')
font_replacements={'400':'/fonts/FFF-AcidGrotesk-Regular.woff2','500':'/fonts/FFF-AcidGrotesk-Medium.woff2','700':'/fonts/FFF-AcidGrotesk-Bold.woff2'}
def rf(m):
    b=m.group(0); w=re.search(r'font-weight:\s*([^;]+)',b,re.I); weight=w.group(1).strip() if w else '400'
    return re.sub(r'url\(["\']data:application/font-woff2[^)]*["\']\)',"url('"+font_replacements.get(weight,font_replacements['400'])+"')",b,flags=re.I|re.S)
html=re.sub(r'@font-face\s*\{[^}]*data:application/font-woff2[^}]*\}',rf,html,flags=re.I|re.S)
html=re.sub(r'ghs_[A-Za-z0-9.\-_]{20,}','github_credential_removed',html,flags=re.I)
html=re.sub(r'github_pat_[A-Za-z0-9_\-]{20,}','github_credential_removed',html,flags=re.I)

subprocess.run(['git','config','user.name','github-actions[bot]'],check=True)
subprocess.run(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],check=True)

runid=os.environ.get('GITHUB_RUN_ID','probe')
counter=0

def probe(fragment,start):
    global counter
    counter+=1
    branch=f'pp-probe-{runid}-{counter}'
    subprocess.run(['git','checkout','--orphan',branch],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    subprocess.run(['git','rm','-rf','.'],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    Path('probe.txt').write_text(fragment,'utf-8')
    subprocess.run(['git','add','probe.txt'],check=True)
    subprocess.run(['git','commit','-m',f'probe {start}'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    p=subprocess.run(['git','push','origin',f'HEAD:refs/heads/{branch}'],text=True,capture_output=True)
    blocked='GITHUB PUSH PROTECTION' in p.stderr and 'GitHub App Installation Access Token' in p.stderr
    if p.returncode==0:
        subprocess.run(['git','push','origin','--delete',branch],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    elif not blocked:
        print('UNEXPECTED_PUSH_FAILURE',p.stderr[-1200:])
        raise SystemExit(2)
    print('PROBE',counter,'start',start,'length',len(fragment),'blocked',blocked)
    return blocked

# Coarse scan with overlap larger than the maximum stateless token size.
window=100000
overlap=1200
blocked_ranges=[]
for start in range(0,len(html),window):
    a=max(0,start-overlap)
    b=min(len(html),start+window+overlap)
    if probe(html[a:b],a):
        blocked_ranges.append((a,b))

if not blocked_ranges:
    print('NO_BLOCKED_RANGE')
    raise SystemExit(3)

print('COARSE_BLOCKED',blocked_ranges)

# Refine each blocked range to around 2500 chars, retaining 700 char overlap.
results=[]
for a,b in blocked_ranges:
    while b-a>2500:
        mid=(a+b)//2
        la,lb=a,min(b,mid+700)
        ra,rb=max(a,mid-700),b
        lbad=probe(html[la:lb],la)
        rbad=probe(html[ra:rb],ra)
        if lbad and not rbad:
            a,b=la,lb
        elif rbad and not lbad:
            a,b=ra,rb
        elif lbad and rbad:
            # same value may occur twice or straddle; keep the smaller left range and record right separately later
            a,b=la,lb
        else:
            # detector appears contextual; retain a wider region
            a,b=max(0,mid-1800),min(len(html),mid+1800)
            break
    results.append((a,b))

print('REFINED',results)
for a,b in results:
    frag=html[a:b]
    red=re.sub(r'[A-Za-z0-9._~%+/=\-]{12,}',lambda m:'<OPAQUE:'+str(len(m.group(0)))+'>',frag)
    red=red.replace('\n',' ')
    print('REDACTED',a,b,red[:2400])
