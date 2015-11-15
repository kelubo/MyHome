int ledpin=9;//定义数字9 接口
int inpin=8;//定义数字8 接口
int val;//定义变量val
void setup() {
  // put your setup code here, to run once:
pinMode(ledpin,OUTPUT);//定义小灯接口为输出接口
pinMode(inpin,INPUT);//定义按键接口为输入接口
}

void loop() {
  // put your main code here, to run repeatedly:
val=digitalRead(inpin);//读取数字8 口电平值赋给val
if(val==LOW)//检测按键是否按下，按键按下时小灯亮起
{ digitalWrite(ledpin,LOW);}
else
{ digitalWrite(ledpin,HIGH);}
}
