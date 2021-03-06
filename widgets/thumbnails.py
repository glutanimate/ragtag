#-*- coding: utf-8 -*-
"""
A widget for displaying a thumbnail grid
"""

import sys
import logging

from PyQt4 import QtCore
from PyQt4 import QtGui

from thumbnailer import Thumbnailmaker
from ImageViewerPopup import ImageViewerPopup


class Thumbnail(QtCore.QObject):
    def __init__(self, imagepath, parent):
        QtCore.QObject .__init__(self, parent=parent)
        self.parent = parent
        self.path = imagepath
        self._thread = None

        self.pool = QtCore.QThreadPool.globalInstance()

        self._qlistview = parent._view
        self._index = None

    def calcThumbnail(self, index, w, h):
        if self._thread:
            # Called during an already running calculation
            return

        self._index = index

        thread = Thumbnailmaker(self.path, w, h)
        self.connect(thread.obj, QtCore.SIGNAL("imageDone"),
                     self.imageDone)
        self.connect(self.parent, QtCore.SIGNAL("stopCalculations"),
                     thread.dontRun)

        #Hold onto a reference to prevent PyQt from dereferencing
        self._thread = thread

        self.pool.start(thread)

    def imageDone(self, image=None):
        if not image:
            logging.warning("Did not get back image from the resizer thread!")
            return

        self._thread = None  # Let the thread die

        thumbPixmap = QtGui.QPixmap()
        thumbPixmap.convertFromImage(image)
        QtGui.QPixmapCache.insert(self.path, thumbPixmap)

        # Tell the QListView widget to update the item that will
        # hold the freshly calculated thumbnail
        self._qlistview.update(self._index)


class ThumbnailDelegate(QtGui.QItemDelegate):
    def __init__(self, parent=None, *args):
        QtGui.QItemDelegate.__init__(self, parent, *args)

    def paint(self, painter, option, index):
        painter.save()

        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        border = True

        option.rect.adjust(4, 4, -4, -4)

        painter.setPen(QtGui.QColor(200, 200, 200))

        thumbnail = index.data(QtCore.Qt.DisplayRole)

        imgPixmap = QtGui.QPixmap()
        if not QtGui.QPixmapCache.find(thumbnail.path, imgPixmap):
            thumbnail.calcThumbnail(index,
                                    option.rect.width(),
                                    option.rect.height())
            painter.setPen(QtGui.QColor(0, 0, 0))
            painter.drawText(option.rect, QtCore.Qt.AlignCenter, "Loading...")
        else:
            imgrect = imgPixmap.rect()

            # Adjust the image to the center both vertically and horizontally
            adj_w = (option.rect.width() - imgrect.width()) / 2.0
            adj_h = (option.rect.height() - imgrect.height()) / 2.0

            option.rect.adjust(adj_w, adj_h, -adj_w, -adj_h)
            if option.state & QtGui.QStyle.State_Selected:
                option.rect.adjust(-2, -2, 2, 2)
                painter.setBrush(QtGui.QBrush(QtCore.Qt.red))
            else:
                painter.setBrush(QtGui.QBrush(QtCore.Qt.white))
            if border:
                option.rect.adjust(-2, -2, 2, 2)
                painter.drawRect(option.rect)
                option.rect.adjust(2, 2, -2, -2)
            painter.drawPixmap(option.rect, imgPixmap)

        painter.restore()

    def sizeHint(self, model, index):
        return QtCore.QSize(160, 160)


class ThumbnailsModel(QtCore.QAbstractListModel):
    def __init__(self, thumbnailpaths, parent=None, *args):
        QtCore.QAbstractListModel.__init__(self, parent, *args)
        self._list = thumbnailpaths

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._list)

    def data(self, index, role):
        if index.isValid() and role == QtCore.Qt.DisplayRole:
            return self._list[index.row()]
        elif index.isValid() and role == QtCore.Qt.ToolTipRole:
            # Show the path of the image as tooltip
            return "<b>Image path:</b>\n" + self._list[index.row()].path
        else:
            return None


class ThumbnailGridView(QtGui.QListView):
    def __init__(self, parent=None):
        QtGui.QListView.__init__(self, parent)

        self.setViewMode(QtGui.QListView.IconMode)

        # Reflow the image grid after resize
        self.setResizeMode(QtGui.QListView.Adjust)

        # Set a few pixel space between the thumbnails
        self.setSpacing(5)

        # All items uses the same size, this supposedly improves performance
        self.setUniformItemSizes(True)

        # Generate images from left to right
        self.setFlow(QtGui.QListView.LeftToRight)

        self.imageviewpopup = ImageViewerPopup()

        self.connect(self, QtCore.SIGNAL("activated (const QModelIndex&)"),
                     self.click)

        # TODO enable this
        #self.addContextMenu()

        # This does not seem to do anything
        # most likely because of QTBUG-7232
        self.setVerticalScrollMode(QtGui.QAbstractItemView.ScrollPerPixel)

    def addContextMenu(self):
        """
        Create & connect the QActions of the right-click menu
        """
        self.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.action1 = QtGui.QAction("Menu item1", self)
        self.addAction(self.action1)
        self.connect(self.action1, QtCore.SIGNAL("triggered()"),
                     self.rightClick)

    def click(self, index):
        """
        Handle the click event on a thumbnail.
        Show the imageviewer popup
        """
        thumbnail = index.data(QtCore.Qt.DisplayRole)

        logging.info("Thumbnail clicked %s", thumbnail.path)

        self.imageviewpopup.setImage(thumbnail.path)
        self.imageviewpopup.show()

    def rightClick(self):
        photo = self.currentIndexToPhoto()
        print photo.path

    def currentIndexToPhoto(self):
        """
        Convert current QModelIndex object to Photo
        """
        # Get the index of the currently selected photo
        index = self.currentIndex()
        # get the object of the currently selected photo
        photoobj = index.data(QtCore.Qt.DisplayRole)

        return photoobj


class Thumbnails(QtGui.QWidget):
    """
    This widget can display a list of images in a thumbnail grid

    slots:
        addImages: takes a list of strings, paths to images
        clearWidget: remove the thumbnals, show empty the widget

    signals:
        stopCalculations: notifies child widgets that the canvas is cleared,
            and do not run any more image resize functions
    """
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        self._view = ThumbnailGridView()
        d = ThumbnailDelegate()
        self._view.setItemDelegate(d)

        # Let Qt decide the ideal thread count
        # only override this with good reason, or debug purposes
        ##self._threadpool = QThreadPool.globalInstance()
        ##self._threadpool.setMaxThreadCount(2)

        layout = QtGui.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._view)

        self.setSizePolicy(QtGui.QSizePolicy.Expanding,
                           QtGui.QSizePolicy.Expanding)

        self.setLayout(layout)

    def addImages(self, imagelist):
        self.emit(QtCore.SIGNAL('stopCalculations'))

        logging.debug("Adding images to thumbview: %s", imagelist)
        m = ThumbnailsModel(
               [Thumbnail(i, parent=self) for i in imagelist])
        self._view.setModel(m)

    def clearWidget(self):
        self.emit(QtCore.SIGNAL('stopCalculations'))

        m = ThumbnailsModel([])
        self._view.setModel(m)

if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    w = Thumbnails()
    w.show()
    app.exec_()
    sys.exit()
