import RPi.GPIO as GPIO
from PCA9685 import PCA9685
import time

class robo:
    pwm = PCA9685()


    def __init__ (self):
        self.pwm.setPWMFreq(50)
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

    def dispatch (self, path, params):
        if path.startswith('/robo/node_no'):
            self.node_no()
        if path.startswith('/robo/node_yes'):
            self.node_yes()
        if path.startswith('/robo/roll_eyes'):
            self.roll_eyes()
        if path.startswith('/robo/head_up'):
            self.head_up()
        if path.startswith('/robo/head_down'):
            self.head_down()
        if path.startswith('/robo/center'):
            self.center()
        if path.startswith('/robo/search'):
            self.search()

    def node_no (self):
        # TODO: run the loop
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down
       
        for i in range (90,60,-3):
            self.pwm.setRotationAngle(1, i) # left/right
            time.sleep(0.05)

        for i in range (60,120,3):
            self.pwm.setRotationAngle(1, i) # left/right
            time.sleep(0.05)

        for i in range (120,90,-3):
            self.pwm.setRotationAngle(1, i) # left/right
            time.sleep(0.05)

    def node_yes (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down
       
        for i in range (90,60,-3):
            self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)

        for i in range (60,120,3):
            self.pwm.setRotationAngle(0, i)
            time.sleep(0.05)

        for i in range (120,90,-3):
            self.pwm.setRotationAngle(0, i)
            time.sleep(0.05)

  
    def head_up (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down
        for i in range (90,20,-3):
            self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)

   
    def head_down (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down
        for i in range (90,160,3):
            self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)
   
    def search (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 40) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 40) # left/right
        self.pwm.setRotationAngle(0, 40) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 40) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 130) # left/right
        self.pwm.setRotationAngle(0, 40) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 130) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 130) # left/right
        self.pwm.setRotationAngle(0, 130) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 130) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 40) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

        time.sleep(0.5)
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

    def center (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down

    def roll_eyes (self):
        self.pwm.setRotationAngle(1, 90) # left/right
        self.pwm.setRotationAngle(0, 90) # up/down
       
        for i in range (90,20,-3):
            self.pwm.setRotationAngle(1, i) # left/right
            self.pwm.setRotationAngle(0, 180-i) # up/down
            time.sleep(0.05)

        for i in range (160,20,3):
            #self.pwm.setRotationAngle(1, i) # left/right
            self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)


        for i in range (20,160,3):
            self.pwm.setRotationAngle(1, i) # left/right
            #self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)

        for i in range (160,90,-3):
            self.pwm.setRotationAngle(1, i) # left/right
            self.pwm.setRotationAngle(0, i) # up/down
            time.sleep(0.05)

 

