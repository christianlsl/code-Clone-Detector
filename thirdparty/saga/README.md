# SAGA

SAGA is a large-scale code clone detection tool. The name comes from "Suffix-Array based clone detection with GPU Acceleration". SAGA is able to detect Type-1/2/3 clones in 100 million lines of code within 11 minutes, with comparable precision and recall to other state-of-the-art tools.

## How to use SAGA

### Requirements

#### Software

- **Supported OS**: Linux/Windows/Mac. Ensure you use the corresponding executable file for your operating system. 
- **Environment**: 
- - Git 
  - JDK 1.8 or higher 
  - NVCC (recommended version: release 12.4, V12.4.99) 
  - Maven (recommended version: 3.6.3)

We have tested SAGA with JDK 1.8.0_181, NVCC V12.4.99 and Maven 3.6.3 on Ubuntu 20.04.6 LTS.

#### Hardware

- Nvidia GPU with at least 4 GB of graphic memory is recommended if using GPU acceleration feature.

### Running SAGA

If you encounter issues with path configurations, use absolute paths for testing.

#### Get the source code of SAGA

```sh
git clone git@github.com:FudanSELab/SAGACloneDetector.git
```

#### <span id="compile">Compile the detection core</span>

```sh
cd /path/to/SAGACloneDetector
nvcc -o executable/sa_gpu scripts/suffix-construct.cu --expt-extended-lambda
```

This will generate an executable file `sa_gpu` in the `SAGACloneDetector/scripts` directory. Part of the directory structure should appear as follows:

```
scripts
├── sa_gpu
└── suffix-construct.cu
```

Note that this core executable utilizes GPU for code clone detection. Nvidia GPU is required.

#### Package `SAGACloneDetector.jar`

```sh
cd /path/to/SAGACloneDetector
mvn package -Dmaven.test.skip=true
mv target/SAGACloneDetector.jar .
```

#### Generate config.properties

````sh
cd /path/to/SAGACloneDetector
# This will generate config.properties in the SAGACloneDetector directory.
java -jar SAGACloneDetector.jar testcase/code/java
````

:exclamation:`config.properties` file must be in the **Working** directory.

```properties
# config.properties
process-build=1
sep-num=100000000
min-line=2
mlcc=20
language=java
threshold=0.7
use-long-type=0
granularity=method
extensions=java
process-parse=1
tokenize=1
thread-num=8
open-string-hash=1
mlc=50
exe=
process-tokenize=1
```

Functions of the parameters are as follows:

```sh
#process-build: Whether execute build process,0 for off, 1 for on
#sep-num: The separator number of token piece
#min-line: The minimum line number of a method
#mlcc: The minimum token number of a snippet
#language: The type of source files(java, c, cpp, py, js, go, common)
#threshold: The threshold of clone detection(0 ~ 1)
#use-long-type: Use long data type to store middle data,0 for int, 1 for long
#granularity: The detection granularity, including file, method, snippet
#extentions: The comma-separated file suffixes
#process-parse: Whether execute parse process,0 for off, 1 for on
#tokenize: Whether tokenize sources files or not, 0 for off, 1 for on
#thread-num: The thread num of parallel suffix array construction
#open-string-hash: Whether open string hash in tokenize progress,0 for close, 1 for open
#mlc: The minimum token number of a method
#exe: The path of executable file
#process-tokenize: Whether execute tokenize process,0 for off, 1 for on
```



#### Update the `exe` Parameter in `config.properties`

Set `exe` to the path of the compiled executable from the [Compile the Executable](#compile) step:

```properties
# config.properties
...
exe=executable/sa_gpu
...
```

#### Run SAGA

```sh
cd /path/to/SAGACloneDetector
java -jar SAGACloneDetector.jar /path/to/DetectedRepoDirectory
```

### Check the outputs (description based on the default paths).

- **logs/**: Stores log files, which are automatically backed up by date.  
- **tokenData/**: Intermediate files, with no direct value.  
- **result/**: Directory for detection result files.

  - **files.txt**: Contains paths of the detected files, filtered based on the configured extensions.  
  - **MeasureIndex.csv** (see details below)  
  - Method-level detection result files (see details below):  

    - **type123_method_result.csv**  
    - **type123_method_group_result.csv**  

  - Snippet-level detection result files (see details below):  

    - **type12_snippet_result.csv**  
    - **type3_snippet_result.csv**  

#### **MeasureIndex.csv**

- Stores information about all the detected methods.  

- Data format: `MethodID, File Path, Start Line, End Line`.  

  ![MeasureIndex.csv](assets/1614242666451-c629acbe-4ffb-4d8a-b949-ad7535c06099.png)

1. **Method-Level Detection Result Files**

   - **type123_method_result.csv**: Contains the results of detected clone pairs.  
   - Data format: `Method1_ID, Method2_ID, Similarity`. 

    ![type123_method_result.csv](assets/1614244476035-60c6845e-a91e-46c2-90a0-1e0c7953a932.png)

   - **type123_method_group_result.csv**: Contains the results of clone groups, which are merged based on clone pairs.

   - Data format: `Method1_ID, Method2_ID, Method3_ID, ...`.

   ![type123_method_group_result.csv](assets/1614244538439-a6887303-a22c-4089-9e88-1c4056b6740b.png)

2. **Snippet-Level Detection Result Files**

   - **type12_snippet_result.csv**: Contains Type-1 and Type-2 clone detection results (for the definition of clone types, see the notes below).  
   - **type3_snippet_result.csv**: Contains Type-3 clone detection results.  
   - The data format for both files is identical:  
     `CloneGroupID, MethodID, File Path, Method Start Line, Method End Line, Snippet Start Position in Method Token Sequence, Snippet End Position in Method Token Sequence, Snippet Start Line, Snippet End Line`.

   ![type3_snippet_result.csv](assets/1614653212861-5783b5ad-8cc8-4297-9c5f-823d87a6320a.png)

   - *Snippet-level detection results are presented as clone pairs. Due to the lack of clear boundaries in snippets, it is not recommended to combine them into clone groups. If needed, you can manually perform the combination.*  

#### **Clone Type Definitions**

- **Type-1**: Identical code fragments, differing only in whitespace, layout, and comments.  
- **Type-2**: Syntactically identical fragments, differing in identifiers, literals, types, whitespace, layout, and comments.  
- **Type-3**: Copied fragments with additional modifications, such as added, changed, or removed statements, along with differences in identifiers, literals, types, whitespace, layout, and comments.  


## Reproducing the results presented in the paper

### Clone BigCloneEval

```sh
git clone git@github.com:jeffsvajlenko/BigCloneEval.git
```

Refer to [BigCloneEval documentation](https://github.com/jeffsvajlenko/BigCloneEval) for steps such as initializing the database and registering tools.

PS: Before `Step 4` of `BigCloneEval`, Modify the code in file `src/cloneMatchingAlgorithms/CoverageMatcher.java` around line 100.

The original code is
```java
		if(tolerence != null) {
			stmt.setInt(12, f1.getStartline() - tolerence);
			stmt.setInt(13, f1.getEndline() + tolerence);
			stmt.setInt(14, f2.getStartline() - tolerence);
			stmt.setInt(15, f2.getEndline() + tolerence);
		} else if(dtolerence != null) {
			stmt.setInt(12, f1.getEndline());
			stmt.setInt(13, f1.getStartline());
			stmt.setInt(14, f2.getEndline());
			stmt.setInt(15, f2.getStartline());
		}
```

It should be

```java
		if(tolerence != null) {
			stmt.setInt(11, f1.getStartline() - tolerence);
			stmt.setInt(12, f1.getEndline() + tolerence);
			stmt.setInt(13, f2.getStartline() - tolerence);
			stmt.setInt(14, f2.getEndline() + tolerence);
		} else if(dtolerence != null) {
			stmt.setInt(11, f1.getEndline());
			stmt.setInt(12, f1.getStartline());
			stmt.setInt(13, f2.getEndline());
			stmt.setInt(14, f2.getStartline());
		}
```


### Copy Scripts to BigCloneEval

```sh
cp /path/to/SAGACloneDetector/scripts/import /path/to/BigCloneEval/commands
```

### Detect Clone Data

```sh
# scan_dir: directory of repos to be scanned
# base_dir: where SAGACloneDetector.jar locates
cd /path/to/SAGACloneDetector/scripts
python detect_merge.py --scan_dir=/path/to/BigCloneEval/ijadataset/bcb_reduced --base_dir=/path/to/SAGACloneDetector
```

### Import Clone Data

```
cd /path/to/BigCloneEval/commands
# Ensure directory Result_2, Result_3 ... exist in /path/to/SAGACloneDetector/verify_result.
./import <YourToolID> /path/to/SAGACloneDetector/verify_result
```

### Export Report

Refer to the [original BigCloneEval repository](https://github.com/jeffsvajlenko/BigCloneEval?tab=readme-ov-file#evaluate) for parameter details.

```sh
./evaluateTool -t <YourToolID> -o <ReportPath> --st BOTH -m "CoverageMatcher 0.7 line 4" --mit 50 --mip 6
```

### Verify data

```sh
less <ReportPath>
```

## About

This repository is maintained by CodeWisdom Team of Fudan University.

You may report bugs by submitting an issue to [the GitHub repository](https://github.com/FudanSELab/SAGACloneDetector) or sending an email to ([wuyijian@fudan.edu.cn](wuyijian:)).
