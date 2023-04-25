% load("ygnet.mat")
delete(imaqfind)
vid=videoinput('winvideo',1);
triggerconfig(vid,'manual');
set(vid,'FramesPerTrigger',1);
set(vid,'TriggerRepeat',Inf)

color_spec=vid.ReturnedColorSpace;

if~strcmp(color_spec,'rgb')
    set(vid,'ReturnedColorSpace','rgb')
end

start(vid)
faceDetector = vision.CascadeObjectDetector;

for ii= 1:600
    trigger(vid)
    img=getdata(vid,1);
    % imshow(img)


    bbox = step(faceDetector, img);

    if~isempty(bbox)
        bbox = bbox(1,:);

        rectangle('Position',bbox,'EdgeColor','b','LineWidth',5);

        FaceCropped = imcrop(img,bbox);
        Face_Resized = imresize(FaceCropped,[227 227]);
        [YPred,scores] = classify(netTransfer,Face_Resized);

        position= [bbox(1) bbox(2)+bbox(4)];
        box_color={'red'};
        a=nominal(YPred)
        pred_tr=cellstr(a);
        img = insertText(img,position,pred_tr,'FontSize',18,'BoxColor',box_color, ...
   'BoxOpacity',0.4,'TextColor','black');
        
        drawnow;
        imshow(img)
    end
end

