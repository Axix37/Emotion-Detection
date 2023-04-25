% load("ygnet.mat");
img=imread('Sans.jpg');
faceDetector = vision.CascadeObjectDetector;

    bbox=step(faceDetector,img);
    
 figure, imshow(img)

 if~isempty(bbox)
        bbox=bbox(1,:);

        rectangle("Position",bbox,'EdgeColor','b','LineWidth',5);

        FaceCropped = imcrop(img,bbox);
 end

 Face_Resized = imresize(FaceCropped,[227 227]);
 [YPred,scores] = classify(netTransfer,Face_Resized);

 a=nominal(YPred)
 pred_tr=cellstr(a);
 position= [0 0;];

 box_color={'red'};
 RGB=insertText(img,position,pred_tr,'FontSize',50,'BoxColor',box_color, ...
   'BoxOpacity',0.4,'TextColor','black');
 figure, imshow(RGB)
  rectangle("Position",bbox,'EdgeColor','b','LineWidth',5);