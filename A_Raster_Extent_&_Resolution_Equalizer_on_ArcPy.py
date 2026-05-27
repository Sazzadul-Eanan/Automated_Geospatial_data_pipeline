# Calling the dependencies
# ─────────────────────────────────────────────
import arcpy
import os

# ─────────────────────────────────────────────
# CONFIGURATION  – Edit the FILE_NAME in first line
# ─────────────────────────────────────────────
input_raster_path = r"G:\Source_Folder\LandUse_2020.tif"    # full path to source raster
output_folder     = r"G:\Source_Folder\Processed_Output"    # auto_created OUTPUT folder within the same directory
TARGET_CELL_SIZE  = 30                                 
# ─────────────────────────────────────────────

# ──Validate input ────────────────────────────────────────────────────────
if not arcpy.Exists(input_raster_path):
    print(f"⚠ arcpy.Exists returned False for: {input_raster_path}")
    print(f"  os.path.exists check            : {os.path.exists(input_raster_path)}")
    raise FileNotFoundError(f"Input raster not found: {input_raster_path}")

os.makedirs(output_folder, exist_ok=True)

# ──Read source raster properties ─────────────────────────────────────────
src = arcpy.Raster(input_raster_path)

spatial_ref = src.spatialReference
pixel_type  = src.pixelType       # e.g. 'U8', 'S16', 'F32' …
is_integer  = src.isInteger
nodata_val  = src.noDataValue     # may be None

# Detect file format from extension so the output keeps the same container
ext       = os.path.splitext(input_raster_path)[1].lower()   # '.tif', '.img', '' …
base_name = os.path.splitext(os.path.basename(input_raster_path))[0]
out_filename = f"{base_name}_processed{ext}"
output_path  = os.path.join(output_folder, out_filename)

# Map internal pixel-type codes → CopyRaster keyword strings
PIXEL_TYPE_MAP = {
    "U1":  "1_BIT",
    "U2":  "2_BIT",
    "U4":  "4_BIT",
    "U8":  "8_BIT_UNSIGNED",
    "S8":  "8_BIT_SIGNED",
    "U16": "16_BIT_UNSIGNED",
    "S16": "16_BIT_SIGNED",
    "U32": "32_BIT_UNSIGNED",
    "S32": "32_BIT_SIGNED",
    "F32": "32_BIT_FLOAT",
    "F64": "64_BIT",
}
copy_pixel_type = PIXEL_TYPE_MAP.get(pixel_type, "32_BIT_FLOAT")
resampling      = "NEAREST" if is_integer else "BILINEAR"

print("─" * 60)
print(f"Input raster   : {input_raster_path}")
print(f"Pixel type     : {pixel_type}  ({'integer' if is_integer else 'float'})")
print(f"Resampling     : {resampling}")
print(f"Output format  : {ext if ext else 'ESRI GRID'}")
print(f"NoData value   : {nodata_val}")
print(f"CRS            : {spatial_ref.name}")
print("─" * 60)

# ──Build a square extent snapped to the 30 m grid ────────────────────────
xmin, ymin = src.extent.XMin, src.extent.YMin
xmax, ymax = src.extent.XMax, src.extent.YMax

width   = xmax - xmin
height  = ymax - ymin
max_dim = max(width, height)

# Ceiling division — number of cells needed to cover the larger dimension
num_cells   = -(-int(max_dim / TARGET_CELL_SIZE))    # rounds up
extent_size = num_cells * TARGET_CELL_SIZE           # exact multiple of 30

# Re-centre on the original data footprint
cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

# Snap corner coordinates to the nearest cell-size boundary
# (prevents floating-point residuals that cause rows ≠ columns by 1)
half     = extent_size / 2
sq_xmin  = (( cx - half) // TARGET_CELL_SIZE) * TARGET_CELL_SIZE
sq_ymin  = (( cy - half) // TARGET_CELL_SIZE) * TARGET_CELL_SIZE
sq_xmax  = sq_xmin + extent_size
sq_ymax  = sq_ymin + extent_size

print(f"Original extent : {width:.2f} m × {height:.2f} m")
print(f"Square extent   : {extent_size:.2f} m × {extent_size:.2f} m")
print(f"Snapped origin  : xmin={sq_xmin:.2f}, ymin={sq_ymin:.2f}")
print(f"Target grid     : {num_cells} × {num_cells} cells @ {TARGET_CELL_SIZE} m")
print("─" * 60)

# ──Set geoprocessing environment (once, no snap raster needed) ────────────
arcpy.env.outputCoordinateSystem = spatial_ref
arcpy.env.extent                 = arcpy.Extent(sq_xmin, sq_ymin, sq_xmax, sq_ymax)
arcpy.env.cellSize               = TARGET_CELL_SIZE
arcpy.env.snapRaster             = None   # fixed mathematical grid; snapping off

# ──Resample to target cell size and square extent ─────────────────────────
temp_path = os.path.join(output_folder, "__temp_resampled.tif")

print("Resampling ...")
arcpy.management.Resample(
    in_raster       = input_raster_path,
    out_raster      = temp_path,
    cell_size       = TARGET_CELL_SIZE,
    resampling_type = resampling,
)

# ──CopyRaster – preserves original pixel type and file format ─────────────
print("Copying and preserving pixel type / format ...")
arcpy.management.CopyRaster(
    in_raster         = temp_path,
    out_rasterdataset = output_path,
    pixel_type        = copy_pixel_type,
    nodata_value      = nodata_val,
    format            = "",    # ArcPy infers format from file extension
)

# Clean up temp file
arcpy.management.Delete(temp_path)

# ──Verify the processed output ──────────────────────────────────────────────────────────
result    = arcpy.Raster(output_path)
out_rows  = result.height
out_cols  = result.width
out_cell  = result.meanCellWidth

print("─" * 60)
print("OUTPUT RASTER PROPERTIES")
print("─" * 60)
print(f"File           : {output_path}")
print(f"Pixel type     : {result.pixelType}  (original was {pixel_type})")
print(f"CRS            : {result.spatialReference.name}")
print(f"Cell size      : {out_cell:.2f} m × {result.meanCellHeight:.2f} m")
print(f"Rows           : {out_rows}")
print(f"Columns        : {out_cols}")

# ──Final equality and cell-size check ───────────────────────────────────────
print("─" * 60)
rows_cols_equal = (out_rows == out_cols)
cellsize_ok     = (round(out_cell) == TARGET_CELL_SIZE)

if rows_cols_equal and cellsize_ok:
    print(f"✓ Rows and columns are both equalized to : {out_rows}")
    print(f"✓ Cell size confirmed at                 : {out_cell:.2f} m")
else:
    if not rows_cols_equal:
        print(f"⚠ Rows ({out_rows}) ≠ Columns ({out_cols}) — extent alignment issue.")
    if not cellsize_ok:
        print(f"⚠ Cell size is {out_cell:.2f} m, expected {TARGET_CELL_SIZE} m.")
print("─" * 60)

