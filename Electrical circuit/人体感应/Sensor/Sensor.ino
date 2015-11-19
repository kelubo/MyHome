int Sensor_pin = 2;
int Buzzerpin = 3;
 
void Alarm() //蜂鸣器发出警报
{
    for(int i=0;i<100;i++){
    digitalWrite(Buzzerpin,HIGH); //发声音
    delay(2);
    digitalWrite(Buzzerpin,LOW); //不发声音
    delay(2); //修改延时时间，改变发声频率
    }
}
 
void setup()
{
    pinMode(Sensor_pin,INPUT); //设置人体红外接口为输入状态
    pinMode(Buzzerpin,OUTPUT); //设置蜂鸣器接口为输出状态
}
 
void loop()
{
    int val=digitalRead(Sensor_pin); //定义参数存储人体红外传感器读到的状态
    if(val == 1) //如果检测到有动物运动（在检测范围内），蜂鸣器发出警报
    { 
        Alarm();
    }
    else
    {
        return;
    } 
    delay(100); //延时100毫秒
}
