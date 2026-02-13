import { IconButton } from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";

export default function UploadButton({ onFilesSelected }) {
  const handleChange = (e) => {
    const files = Array.from(e.target.files);
    if (files.length > 0) {
      onFilesSelected(files);
    }
    e.target.value = null;
  };

  return (
    <label htmlFor="upload-file">
      <input
        style={{ display: "none" }}
        id="upload-file"
        type="file"
        accept=".nc"
        multiple
        onChange={handleChange}
      />
      <IconButton color="primary" component="span">
        <CloudUploadIcon />
      </IconButton>
    </label>
  );
}
