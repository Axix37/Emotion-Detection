% code to convert my greyscale image to rbg
input_folder = 'train';
output_folder = 'Train3';

% Create an ImageDatastore object for the input folder
imds_input = imageDatastore(input_folder, 'IncludeSubfolders', true, 'LabelSource', 'foldernames');

% Create the output folder if it doesn't already exist
if ~exist(output_folder, 'dir')
    mkdir(output_folder);
end

% Loop over each labeled image in the input ImageDatastore
for i = 1:numel(imds_input.Files)
    % Read the input image from the input ImageDatastore using readimage
    img = readimage(imds_input, i);
    
    % Convert the image to RGB using cat
    rgb_img = cat(3, img, img, img);
    
    % Get the full file path of the current input image
    input_file_path = imds_input.Files{i};
    
    % Get the corresponding output file path based on the input file path
    output_file_path = strrep(input_file_path, input_folder, output_folder);
    
    % Create the output folder for the current image if it doesn't already exist
    [output_folder_path, ~, ~] = fileparts(output_file_path);
    if ~exist(output_folder_path, 'dir')
        mkdir(output_folder_path);
    end
    
    % Save the RGB image to the output folder using imwrite
    imwrite(rgb_img, output_file_path);
end

