from bs4 import BeautifulSoup
from urllib.parse import urlparse,parse_qs
import requests
import re,math,os,random,sys,argparse,datetime

SAVE_LOCATION=os.path.expanduser(os.path.join("~","macciesbigmacify"))
SAVED_CODES=os.path.join(SAVE_LOCATION,"codes.txt")

#reversing the url so you canne just search this feckin thing if I make it public
MCD_URL="moc.sthguohtrofdoofdcm//:sptth"[::-1]
INDEX_URL="Index.aspx"
SURVEY_URL="Survey.aspx"
COOKIE_AADCS="AspxAutoDetectCookieSupport"
CONTENT_FORM="application/x-www-form-urlencoded"
SURVEY_FORM_1="surveyEntryForm"
SURVEY_FORM_2="surveyForm"
PAY_JS="JavaScriptEnabled"
PAY_RECEIPT="Receipt"
PAY_CODE=["CN1","CN2","CN3"]
PAY_PRICE=("Pound","Pence")
DEFAULT_UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36"

def tryint(v,default=0):
    try:return int(v)
    except ValueError:return default
def tryval(v):
    try:return int(v)
    except ValueError:return v
def extract_input_data(inputs):
    dat={}
    for i in inputs:
        iv=i["value"]
        ivi=tryint(iv,None)
        if type(ivi)==int:iv=ivi
        dat[i["name"]]=iv
    return dat
def get_input_data(form):return extract_input_data(form.find_all("input"))
def get_hidden_inputs(form):return extract_input_data(form.find_all("input",type="hidden"))
def parse_action(act,return_path=True):
    uparse=urlparse(act)
    a1=parse_qs(uparse.query)
    k=list(a1.keys())[0]
    res={k:"".join(a1[k])}
    return uparse.path,res if return_path else res
#compare strings if equal
def subcase(a,b):
    return a.lower()==b.lower()
def parse_code(c):
    c=c.replace("-","").replace(" ","").upper()
    if len(c)!=12:raise ValueError("Code not right length")
    return [c[i*4:i*4+4]for i in range(3)]
#return pound,pence
def parse_price(p):
    if isinstance(p,str):p=float(re.findall('\d*\.?\d+',p)[0])
    p=math.modf(p)
    return int(p[1]),int(p[0]*100)

#fills in first 3 screens of form (cookie confirmation, receipt available, code/price)
#code = 3 part tuple (1,2,3)
#price = 2 part tuple (pound, pence)
#returns first parsed survey
def start_survey(session,code,price):
    if isinstance(code,str):code=parse_code(code)
    if isinstance(price,float)or isinstance(price,str):price=parse_price(price)
    if len(code)!=3:raise ValueError("Code tuple is not correct size %s"%code)
    if len(price)!=2:raise ValueError("Price tuple is not correct size %s"%price)
    res1=session.get(MCD_URL,params={COOKIE_AADCS:1},headers={"Cookie":"{0}=1".format(COOKIE_AADCS)})
    res1_parsed=BeautifulSoup(res1.content,"html.parser")
    res1_survey_form=res1_parsed.find(id=SURVEY_FORM_1)
    res2_submit_data=get_input_data(res1_survey_form)
    #ensure that server thinks JS enabled
    if PAY_JS in res2_submit_data:res2_submit_data[PAY_JS]=1
    #should submit as urlencoded form
    res2_url,res2_params=parse_action(res1_survey_form["action"])
    res2=session.post(MCD_URL+"/%s"%INDEX_URL,params=res2_params,data=res2_submit_data)
    res2_parsed=BeautifulSoup(res2.content,"html.parser")
    res2_survey_form=res2_parsed.find(id=SURVEY_FORM_1)
    res2_inputs=get_input_data(res2_survey_form)
    if PAY_JS in res2_inputs:res2_inputs[PAY_JS]=1
    if PAY_RECEIPT in res2_inputs:res2_inputs[PAY_RECEIPT]=1
    res3_url,res3_params=parse_action(res2_survey_form["action"])
    res3=session.post(MCD_URL+"/%s"%INDEX_URL,params=res3_params,data=res2_inputs)
    res3_parsed=BeautifulSoup(res3.content,"html.parser")
    res3_form=res3_parsed.find(id=SURVEY_FORM_1)
    res3_values=get_input_data(res3_form)
    if PAY_JS in res3_values:res3_values[PAY_JS]=1
    for i,c in enumerate(PAY_CODE):res3_values[c]=code[i]
    for i,p in enumerate(PAY_PRICE):res3_values[p]=price[i]
    #now test if code/price work
    #will redirect to Index GET request if data doesn't fit
    res4_url,res4_params=parse_action(res3_form["action"])
    res4=session.post(MCD_URL+"/%s"%SURVEY_URL,params=res4_params,data=res3_values)
    #redirected, meaning error on submitting data
    #on success, returns survey form for post
    if len(res4.history)>0:raise ValueError("Supplied information is invalid for Survey")
    res4_parsed=BeautifulSoup(res4.content,"html.parser")
    return parse_survey(res4_parsed)

def extract_int(s):return re.findall(r'\d+',s)

def extract_code(bs_page):
    codes=bs_page.find_all(class_="ValCode")
    if len(codes)>0:
        cont=""
        if not codes[0].string:
            if len(codes[0].contents)>0:cont=codes[0].contents[0]
            else:return
        else:cont=codes[0].string
        code="".join(extract_int(cont))
        return code

#gets timestamp YYYYMMDD HHmmSS
def get_timestamp():return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

#BeautifulSoup object for the form
#returns
#0 - path - str - the POST location for the form
#1 - params - dict - the POST params
#2 - progress - int - parsed percentage of survey completion
#3 - form_title - str - part of form
#4 - form_question - int - type of form question
#5 - question_ret - dict - extracted form data (for use with choosing answers)
#6 - other_form_data - dict
#other
def parse_survey(survey_page):
    survey_form=survey_page.find(id=SURVEY_FORM_2)
    path,params=parse_action(survey_form["action"])
    progress=survey_form.find(id="ProgressPercentage")
    if progress:
        #try parse progress as int, otherwise set progress to None (I.e. couldn't parse)
        try:progress=int(progress.text.strip("%"))
        except:progress=None
    #other hidden inputs and the like
    other_form_data={}
    #form questions
    form_title=""
    form_question=0
    questions={}
    checkboxes={"choices":[],"values":{},"readable":{}}
    labels={}
    #check if form has title (Please rate your satisfaction etc...)
    tdiv=survey_form.find("div", {"class":"blocktitle"})
    if tdiv:form_title=tdiv.text
    #extract labels for questions
    for lab in survey_form.find_all("label"):
        if "for" in lab.attrs:labels[lab["for"]]=lab.text
    for inp in survey_form.find_all("input"):
        if inp["type"]=="radio":
            form_question=1
            n=inp["name"]
            #in questions as radio group
            if not n in questions:questions[n]={"question":None,"choices":[],"readable":{}}
            val=tryval(inp["value"])
            questions[n]["choices"].append(val)
            if "aria-labelledby" in inp.attrs:
                ar=inp["aria-labelledby"].split()
                arcorrect=len(ar)>=2
                #find question text
                if arcorrect:
                    #if not none then set by previous iteration
                    if questions[n]["question"]==None:
                        qdiv=survey_form.find(id=ar[0])
                        if qdiv:questions[n]["question"]=qdiv.text
                    valdiv=survey_form.find(id=ar[1])
                    if valdiv:questions[n]["readable"][valdiv.text]=val
            else:
                if inp["id"] in labels:
                    questions[n]["readable"][labels[inp["id"]]]=val
                if questions[n]["question"]==None:
                    fnsdiv=survey_form.find(id="FNS%s"%n)
                    if fnsdiv:
                        tdiv=fnsdiv.find("div",{"class":"FNSText"})
                        if tdiv:questions[n]["question"]=tdiv.text
        elif inp["type"]=="checkbox":
            form_question=2
            #checkboxes not grouped
            iname=inp["name"]
            #if not n in questions:questions[n]={"type":"checkbox","choices":[],"values":{},"readable":{}}
            checkboxes["choices"].append(iname)
            checkboxes["values"][iname]=tryval(inp["value"])
            if inp["id"] in labels:checkboxes["readable"][iname]=labels[iname]
        elif inp["type"]=="hidden":
            #other_form_data.append((inp["name"],tryint(inp["value"],inp["value"])))
            other_form_data[inp["name"]]=tryint(inp["value"],inp["value"])
    if form_question==0:
        #check if textarea input
        textarea=survey_form.find("textarea")
        form_question=3
        if textarea:
            form_title=labels[textarea["name"]]
    #radio group, checkboxes, textarea/not parsed
    if form_question==1:question_ret=questions
    elif form_question==2:question_ret=checkboxes
    else:question_ret=None
    return path,params,progress,form_title,form_question,question_ret,other_form_data
def eqnocase(a,b):return a.lower()==b.lower()
def choose_answers(question_type,questions,answers):
    resdata={}
    #text box
    if question_type==3:return resdata
    elif question_type==2:
        #checkbox answers, disabling for now as not required in final product, may add in future
        if not "checkbox" in answers:return resdata
    elif question_type==1:
        for question_id in questions:
            q=questions[question_id]
            qs=q["question"]
            ans=q["choices"]
            sans=[r for r in q["readable"]]
            rans=[r.lower() for r in q["readable"]]
            answers_supplied=False
            for ansx in answers["radio"]:
                #question in predefined answers
                if ansx[0].lower() in qs.lower():
                    #extract answers that match in parsed 'readable' answers
                    anschoices=[]
                    for ri,r in enumerate(rans):
                        for ay in ansx[1]:
                            if ay.lower() in r:anschoices.append(sans[ri])
                    #throw error, shouldn't happen. Diagnose if do
                    if len(anschoices)==0:raise ValueError("Failed to choose answer")
                    resdata[question_id]=random.choice(anschoices)
                    break
            if answers_supplied:continue
            else:
                #determine if choosing rating (Highly likely etc...)
                #choose the highest value as to avoid future questions regarding why lower value chosen
                h="highly"
                rating_keywords=("likely","valued","satisfied")
                for rat in rating_keywords:
                    j="%s %s"%(h,rat)
                    if j in rans:
                        #get value of 'readable' highly likely
                        resdata[question_id]=ans[rans.index(j)]
                        answers_supplied=True
                        break
            #if question not predetermined or a rating then choose random answer and hope for the best
            if not answers_supplied:resdata[question_id]=random.choice(ans)
        return resdata
answers={
    "radio":[ #full questions aren't needed as it checks if string is inside question
        ("was your visit type", ("drive-thru","takeaway")),
        ("was your order accurate",("yes")),
        ("did you customise your order",("no")),
        ("did a crew member ask you to check your order",("no")),
        ("did you experience a problem",("no")),
        ("were you asked to wait for your order",("no")), #in the carpark
        ("were you asked to pull forward",("no")), #at the collection window, were you asked to pull forward to the next window to wait for your order
        ("would you like to recognise a staff member",("no")) #for providing great service
    ]
}

#questions in predetermined answers are not full as check if text is inside the parsed form

def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("code",help="The McDonalds receipt code")
    p.add_argument("price",help="The total cost on the receipt")
    a=p.parse_args()
    return parse_code(a.code),parse_price(a.price)
def main():
    #parameters supplied, use Argparse
    code=price=None
    if len(sys.argv)>1:code,price=parse_args()
    else:
        code=parse_code(input("Receipt code: "))
        price=parse_price(input("Total price: "))
    if code and price:
        #More like Old Sprice amirite
        sprice="£%{0}.{1}".format(*price)
        print("Successfully parsed code and price, starting survey")
        s=requests.Session()
        s.headers["User-Agent"]=DEFAULT_UA
        #returns parsed survey on success, otherwise raises Value Error inside function
        surv=start_survey(s,code,price)
        count=1
        while True:
            spath=surv[0]
            sparams=surv[1]
            prog=surv[2]
            formdata=surv[6]
            #print("Page %s"%count)
            #Print question
            """
            if surv[5]:
                for q in surv[5]:
                    if "question" in surv[5][q]:print("\t%s"%surv[5][q]["question"])
            """
            answer_data=choose_answers(surv[4],surv[5],answers)
            formdata.update(answer_data)
            postRes=s.post("%s/%s"%(MCD_URL,spath),params=sparams,data=formdata)
            finalUrl=urlparse(postRes.url)
            if "finish" in finalUrl.path.lower():
                print("Completed survey")
                #print(postRes.content)
                offer_code=extract_code(BeautifulSoup(postRes.content,"html.parser"))
                if not os.path.exists(SAVE_LOCATION):os.makedirs(SAVE_LOCATION,exist_ok=True)
                if offer_code:
                    print("Offer Code: %s"%offer_code)
                    with open(SAVED_CODES,'a')as out:
                        out.write("%s - %s £%s = %s\r\n"%(get_timestamp(),"-".join(code),sprice,offer_code))
                    print("Saved to %s"%SAVED_CODES)
                else:
                    print("Failed to parse final page, saving HTML page")
                    output_file=os.path.join(SAVE_LOCATION,"finishpage_%s.html"%get_timestamp())
                    with open(output_file,'wb')as out:
                        out.write(postRes.content)
                break
            else:
                #and carry on the loop
                surv=parse_survey(BeautifulSoup(postRes.content,"html.parser"))
            count+=1
            #redirects to Finish.aspx on completion

if __name__=="__main__":
    main()
