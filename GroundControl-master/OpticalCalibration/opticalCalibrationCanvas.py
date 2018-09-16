from kivy.uix.gridlayout                     import GridLayout
from kivy.properties                         import NumericProperty, ObjectProperty, BooleanProperty
from kivy.graphics                           import Color, Ellipse, Line
from kivy.graphics.texture                   import Texture
from kivy.graphics.transformation            import Matrix
from kivy.core.window                        import Window
from kivy.graphics.transformation            import Matrix
from kivy.clock                              import Clock
from kivy.uix.image                          import Image
from kivy.app                                import   App
from Settings                                import maslowSettings
from functools                               import partial
from scipy.spatial                           import distance as dist
from imutils                                 import perspective
from imutils                                 import contours
import numpy                                 as np
import imutils
import cv2
import time
import re
import math
import global_variables

class KivyCamera(Image):
    def __init__(self, **kwargs):
        super(KivyCamera, self).__init__(**kwargs)
        self.capture = None

    def start(self, capture, fps=30):
        self.capture = capture
        Clock.schedule_interval(self.update, 1.0 / fps)

    def stop(self):
        Clock.unschedule_interval(self.update)
        self.capture = None

    def update(self, dt):
        ret, frame = self.capture.read()
        if ret:
            # convert it to texture
            buf1 = cv2.flip(frame, 0)
            buf = buf1.tostring()
            image_texture = Texture.create(
                size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
            image_texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
            # display image from the texture
            self.texture = image_texture

    def getCapture(self):
        return self.capture.read()

#capture = None

class MeasuredImage(Image):
    def __init__(self, **kwargs):
        super(MeasuredImage, self).__init__(**kwargs)

    def update(self, frame):
        cv2.imwrite("measuredImage.png",frame)
        buf1 = cv2.flip(frame,0)
        buf = buf1.tostring()
        image_texture = Texture.create(
            size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
        image_texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
        # display image from the texture
        self.texture = image_texture

class OpticalCalibrationCanvas(GridLayout):

    capture = None
    refObj = None
    D = 0
    done = ObjectProperty(None)
    currentX, currentY = 0, 0
    calX = 0
    calY = 0
    matrixSize = (31, 15)
    calErrorsX = np.zeros(matrixSize)
    calErrorsY = np.zeros(matrixSize)
    _calErrorsX = np.zeros(matrixSize)
    _calErrorsY = np.zeros(matrixSize)

    markerWidth         = 0.5*25.4
    inAutoMode = False
    inAutoModeForFirstTime = True


    #def initialize(self):

    def initialize(self):
        xyErrors = self.data.config.get('Computed Settings', 'xyErrorArray')
        self.calErrorsX, self.calErrorsY = maslowSettings.parseErrorArray(xyErrors, True)
        #print str(xErrors[2][0])
        self.capture = cv2.VideoCapture(0)
        if self.capture.isOpened():
            self.ids.KivyCamera.start(self.capture)
        else:
            print "Failed to open camera"


    def on_stop(self):
        self.capture.release()

    def midpoint(self, ptA, ptB):
        return ((ptA[0]+ptB[0])*0.5, (ptA[1]+ptB[1])*0.5)

    def do_Exit(self):
        if self.capture != None:
            self.capture.release()
            self.capture = None
            self.parent.parent.parent.dismiss()

    def on_MoveandMeasure(self, doCalibrate, _posX, _posY):
        if _posX != None:
            #move to posX, posY.. put in absolute mode
            self.currentX = _posX#+15
            self.currentY = _posY#7-_posY
            print "_posX="+str(_posX)+", _posY="+str(_posY)
            posX = _posX*3.0
            posY = _posY*3.0
            #posX=self.calPositionsX[posX]
            #posY=self.calPositionsY[posY]
            print "posX="+str(posX)+", _posY="+str(posY)
            if posY >= -18 and posY <= 18  and posX >= -42 and posX <= 42:
                print "Moving to:[{}, {}]".format(posX,posY)
                self.data.units = "INCHES"
                self.data.gcode_queue.put("G20 ")
                self.data.gcode_queue.put("G90  ")
                self.data.gcode_queue.put("G0 X"+str(posX)+" Y"+str(posY)+"  ")
                self.data.gcode_queue.put("G91  ")
                if doCalibrate:
                    self.data.measureRequest = self.on_MeasureandCalibrate
                else:
                    self.data.measureRequest = self.on_MeasureOnly
                #request a measurement
                self.data.gcode_queue.put("B10 L")

    def on_AutoMeasure(self):
        self.inAutoMode = True
        if (self.inAutoModeForFirstTime==True):
            self.currentX=-1
            self.currentY=1
            self.inAutoModeForFirstTime=False
        else:
            self.currentX += 1
            if (self.currentX==2):
                self.currentX = -1
                self.currentY -= 1
        if (self.currentY!=-2):
            self.on_MoveandMeasure(False, self.currentX, self.currentY)
        else:
            self.inAutoMode = False

    def on_MeasureandCalibrate(self, dist):
        print "MeasureandCalibrate"
        time.sleep(2)
        self.on_Measure(True)

    def on_MeasureOnly(self, dist):
        print "MeasureOnly"
        timer = time.time()+2
        while time.time()<timer:
            dummy = 5
        self.on_Measure(False)

    def on_Measure(self, doCalibrate):
        print "here at measure"
        ret, image = self.ids.KivyCamera.getCapture()
        if ret:
            self.ids.MeasuredImage.update(image)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            edged = cv2.Canny(gray, 50, 100)
            edged = cv2.dilate(edged, None, iterations=1)
            edged = cv2.erode(edged, None, iterations=1)
            cnts = cv2.findContours(edged.copy(), cv2.RETR_EXTERNAL,
	           cv2.CHAIN_APPROX_SIMPLE)
            cnts = cnts[0] if imutils.is_cv2() else cnts[1]
            (cnts, _) = contours.sort_contours(cnts)
            colors = ((0, 0, 255), (240, 0, 159), (0, 165, 255), (255, 255, 0), (255, 0, 255))
            refObj = None
            height, width, channels = image.shape
            xA = int(width/2)
            yA = int(height/2)

            orig = image.copy()
            for c in cnts:
            	# if the contour is not sufficiently large, ignore it

            	if cv2.contourArea(c) < 100:
            		continue

            	# compute the rotated bounding box of the contour
            	box = cv2.minAreaRect(c)
            	box = cv2.cv.BoxPoints(box) if imutils.is_cv2() else cv2.boxPoints(box)
            	box = np.array(box, dtype="int")

            	# order the points in the contour such that they appear
            	# in top-left, top-right, bottom-right, and bottom-left
            	# order, then draw the outline of the rotated bounding
            	# box
            	box = perspective.order_points(box)

            	# compute the center of the bounding box
            	cX = np.average(box[:, 0])
            	cY = np.average(box[:, 1])

                if doCalibrate:
                    (tl, tr, br, bl) = box
                    (tlblX, tlblY) = self.midpoint(tl, bl)
                    (trbrX, trbrY) = self.midpoint(tr, br)

                    self.D = dist.euclidean((tlblX,tlblY),(trbrX,trbrY))/self.markerWidth
                    print "Distance = "
                    print self.D
                    self.ids.OpticalCalibrationMeasureButton.disabled = False
                    self.ids.OpticalCalibrationAutoMeasureButton.disabled = False
                    self.ids.OpticalCalibrationDistance.text = "mm/Pixel: {:.3f}".format(self.D)
                    self.inAutoModeForFirstTime = True

            	cv2.drawContours(orig, [box.astype("int")], -1, (0, 255, 0), 2)

            	# stack the reference coordinates and the object coordinates
            	# to include the object center
            	objCoords = np.vstack([box, (cX, cY)])

            	#for ((xB, yB), color) in zip(objCoords, colors):
            	# draw circles corresponding to the current points and
            	# connect them with a line
                xB = cX
                yB = cY
                cv2.circle(orig, (int(xB), int(yB)), 5, colors[0], -1)
                cv2.line(orig, (xA, yA), (int(xB), int(yB)), colors[0], 2)
                Dist = dist.euclidean((xA, yA), (xB, yB)) / self.D
                Dx = dist.euclidean((xA,0), (xB,0))/self.D
                if (xA>xB):
                    Dx *= -1
                Dy = dist.euclidean((0,yA), (0,yB))/self.D
                if (yA<yB):
                    Dy *= -1
                (mX, mY) = self.midpoint((xA, yA), (xB, yB))
                cv2.putText(orig, "{:.3f}, {:.3f}->{:.3f}mm".format(Dx,Dy,Dist), (int(mX), int(mY - 10)),cv2.FONT_HERSHEY_SIMPLEX, 0.55, colors[0], 2)
                if doCalibrate:
                    print "At calX,calY"
                    self.calX=Dx
                    self.calY=Dy
                else:
                    self.calErrorsX[self.currentX+15][7-self.currentY] = Dx#-self.calX
                    self.calErrorsY[self.currentX+15][7-self.currentY] = Dy#-self.calY

                self.ids.OpticalCalibrationDistance.text = "Pixel\mm: {:.3f}\nCal Error({:.3f},{:.3f})\n".format(self.D, self.calX, self.calY)
                self.ids.OpticalCalibrationDistance.text += "[{:.3f},{:.3f}] [{:.3f},{:.3f}] [{:.3f},{:.3f}]\n".format(self.calErrorsX[14][6], self.calErrorsY[14][6], self.calErrorsX[15][6], self.calErrorsY[15][6], self.calErrorsX[16][6], self.calErrorsY[16][6])
                self.ids.OpticalCalibrationDistance.text += "[{:.3f},{:.3f}] [{:.3f},{:.3f}] [{:.3f},{:.3f}]\n".format(self.calErrorsX[14][7], self.calErrorsY[14][7], self.calErrorsX[15][7], self.calErrorsY[15][7], self.calErrorsX[16][7], self.calErrorsY[16][7])
                self.ids.OpticalCalibrationDistance.text += "[{:.3f},{:.3f}] [{:.3f},{:.3f}] [{:.3f},{:.3f}]\n".format(self.calErrorsX[14][8], self.calErrorsY[14][8], self.calErrorsX[15][8], self.calErrorsY[15][8], self.calErrorsX[16][8], self.calErrorsY[16][8])

            print "Updating MeasuredImage"
            #cv2.imshow("Image", orig)
            self.ids.MeasuredImage.update(orig)
            if (self.inAutoMode):
                self.on_AutoMeasure()

    def on_SaveAndSend(self):
        _str = ""
        _strcomma = ""
        for z in range(2):
            for y in range(15):
                for x in range(31):
                    if ((x==30) and (y==14) and (z==1)):
                        _strcomma = ""
                    else:
                        _strcomma = ","
                    if (z==0):
                        _str += str(int(self.calErrorsX[x][y]*1000))+_strcomma
                    else:
                        _str += str(int(self.calErrorsY[x][y]*1000))+_strcomma
        print _str
        App.get_running_app().data.config.set('Computed Settings', 'xyErrorArray', _str)
