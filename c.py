# -*- coding: utf-8 -*-
import cv2

# マウスイベント時に処理を行う
def mouse_event(event, x, y, flags, param):

    # 左クリックで赤い円形を生成
    if event == cv2.EVENT_LBUTTONUP:
        cv2.circle(img, (x, y), 50, (0, 0, 255), -1)

    # 右クリック + Shiftキーで緑色のテキストを生成
    elif event == cv2.EVENT_RBUTTONUP and flags & cv2.EVENT_FLAG_SHIFTKEY:
        cv2.putText(img, "CLICK!!", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 255, 0), 3, cv2.CV_AA)

    # 右クリックのみで青い四角形を生成
    elif event == cv2.EVENT_RBUTTONUP:
        cv2.rectangle(img, (x-100, y-100), (x+100, y+100), (255, 0, 0), -1)


# 画像の読み込み
img = cv2.imread("shako.jpg", 1)
# ウィンドウのサイズを変更可能にする
cv2.namedWindow("img", cv2.WINDOW_NORMAL)
# マウスイベント時に関数mouse_eventの処理を行う
cv2.setMouseCallback("img", mouse_event)

# 「Q」が押されるまで画像を表示する
while (True):
    cv2.imshow("img", img)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cv2.destroyAllWindows()
