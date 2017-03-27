#!/bin/bash

function generate_jobs()
{
    test_name=$1
    distro=$2
    harddisk_flag=$3
    pwd
	for PLAT in $SHELL_PLATFORM 
	do
    	board_arch=${dict[$PLAT]}
        if [ x"$distro" != x"" ]; then
    		python estuary-ci-job-creator.py $FTP_SERVER/${TREE_NAME}/${GIT_DESCRIBE}/${PLAT}-${board_arch}/ --plans $test_name --distro $distro $harddisk_flag
        else 
        	python estuary-ci-job-creator.py $FTP_SERVER/${TREE_NAME}/${GIT_DESCRIBE}/${PLAT}-${board_arch}/ --plans $test_name 
        fi
   		if [ $? -ne 0 ]; then
    		echo "create the boot jobs error! Aborting"
       		return -1
    	fi
	done
}

function run_and_report_jobs()
{
	pushd ${JOBS_DIR}
	python ../estuary-job-runner.py --username $LAVA_USER --token $LAVA_TOKEN --server $LAVA_SERVER --stream $LAVA_STREAM --poll POLL
	popd

	if [ ! -f ${JOBS_DIR}/${RESULTS_DIR}/POLL ]; then
		echo "Running jobs error! Aborting"
    	return -1
	fi

	python estuary-report.py --boot ${JOBS_DIR}/${RESULTS_DIR}/POLL --lab $LAVA_USER

	if [ ! -d ${RESULTS_DIR} ]; then
		echo "running jobs error! Aborting" 
		return -1
	fi
}

function judge_pass_or_not()
{
	FAIL_FLAG=$(grep -R 'FAIL' ./${JOBS_DIR}/${RESULTS_DIR}/POLL)
	if [ "$FAIL_FLAG"x != ""x ]; then
		echo "jobs fail"
	    return -1
	fi

	PASS_FLAG=$(grep -R 'PASS' ./${JOBS_DIR}/${RESULTS_DIR}/POLL)
	if [ "$PASS_FLAG"x = ""x ]; then
		echo "jobs fail"
	    return -1
	fi
}

function run_and_move_result()
{
	test_name=$1
    dest_dir=$2
    run_and_report_jobs 
	[ $? -ne 0 ] && return -1

	judge_pass_or_not
	[ $? -ne 0 ] && return -1
	[ -d ${JOBS_DIR} ] && mv ${JOBS_DIR} ${JOBS_DIR}_${test_name}
    [ -d ${RESULTS_DIR} ] && mv ${RESULTS_DIR} ${RESULTS_DIR}_${test_name}
    [ ! -d ${dest_dir} ] && mkdir -p ${dest_dir}
    [ -d ${JOBS_DIR}_${test_name} ] && mv ${JOBS_DIR}_${test_name} ${dest_dir}
	[ -d ${RESULTS_DIR}_${test_name} ] && mv ${RESULTS_DIR}_${test_name} ${dest_dir}
}

function print_time()
{
	echo -e $@ `date "+%Y-%m-%d %H:%M:%S"` "\n" >> $timefile
    #echo -e "\n"  >> $timefile
}

export

#######  Begining the tests ######
timefile=${WORKSPACE}/timestamp_boot.txt
if [ -f ${timefile} ]; then
	rm -fr $timefile
else
	touch $timefile
fi

if [ -f ${WORKSPACE}/whole_summary.txt ]; then
	rm -rf ${WORKSPACE}/whole_summary.txt
else
	touch ${WORKSPACE}/whole_summary.txt
fi 


print_time "the begin time of boot test is "

##### copy some files to the lava-server machine to support the boot process #####
set -e
set -x

CI_SCRIPTS_DIR=${WORKSPACE}/local/ci-scripts
pushd ${CI_SCRIPTS_DIR}/boot-app-scripts    # change current work directory


test -d $GIT_DESCRIBE && rm -fr $GIT_DESCRIBE

echo $TFTP_DIR
cp download_all_file.py download_distros.sh $TFTP_DIR


if [ $? -ne 0 ]; then
	echo 'Upload download tools failed'
    exit -1
fi

ESTUARY_DIR=estuary
BOOT_LOC=/targetNFS/ubuntu_for_deployment/sys_setup/bin
BOOT_DIR=/targetNFS/ubuntu_for_deployment/sys_setup/boot
ESTUARY_CI_DIR=estuary_ci_files
JOBS_DIR=jobs
RESULTS_DIR=results

(
    cd $TFTP_DIR
    [ -d ${ESTUARY_DIR} ] && rm -fr ${ESTUARY_DIR}
    mkdir ${ESTUARY_DIR}
	cd $TFTP_DIR/${ESTUARY_DIR}
    python ../download_all_file.py -u $FTP_SERVER -d $GIT_DESCRIBE -j $TREE_NAME
    SATA_IMAGE_DIR=sata_image
    [ -d ${SATA_IMAGE_DIR} ] && rm -fr ${SATA_IMAGE_DIR}
    mkdir ${SATA_IMAGE_DIR}
    for file in *; do
    	if [ x"$(expr match "$file" '.*\(-sata\).*')" != x"" ]; then
        	mv $file ./${SATA_IMAGE_DIR}/${file/-sata/}
        fi
    done
    [ -d /home/$USER/${ESTUARY_CI_DIR} ] && sudo rm -fr /home/$USER/${ESTUARY_CI_DIR}
    sudo mkdir /home/$USER/${ESTUARY_CI_DIR}
    if [[ ${SHELL_PLATFORM} =~ "D02" ]] || [[ ${SHELL_PLATFORM} =~ "d02" ]];then 
    sudo cp -rf *dtb *Image* mini* ${SATA_IMAGE_DIR} /home/$USER/${ESTUARY_CI_DIR}
    else
    sudo cp -rf *Image* mini* ${SATA_IMAGE_DIR} /home/$USER/${ESTUARY_CI_DIR}
    fi
	#sudo cp -rf *dtb *Image* mini* ${SATA_IMAGE_DIR} /home/$USER/${ESTUARY_CI_DIR}
    rm -fr download_all_file.py
)

(
    cd $TFTP_DIR/${ESTUARY_DIR}
	if [ ${SHELL_PLATFORM} =~ "D02" -o ${SHELL_PLATFORM} =~ "d02" ];then 
    echo "SHELL_PLATFORM = D02"
    sudo cp -f *.dtb *Image* $BOOT_LOC
    sudo cp -f *.dtb *Image* $BOOT_DIR
    else
    echo "SHELL_PLATFORM >= D03"
    sudo cp -f  *Image* $BOOT_LOC
    sudo cp -f  *Image* $BOOT_DIR    
    fi
)

read -a arch <<< $(echo $ARCH_MAP)
declare -A dict
for((i=0; i<${#arch[@]}; i++))
do
    if ((i%2==0)); then
        j=`expr $i+1`
        dict[${arch[$i]}]=${arch[$j]}
    fi
done

SHELL_PLATFORM="$(echo $SHELL_PLATFORM | tr '[:upper:]' '[:lower:]')"

for DISTRO in $SHELL_DISTRO;
do
	for PLAT in $SHELL_PLATFORM;
    do
    	board_arch=${dict[$PLAT]}
        URL_NAME=$FTP_SERVER/${TREE_NAME}/${GIT_DESCRIBE}/${PLAT}-${board_arch}
        (
            cd $TFTP_DIR
            sudo ./download_distros.sh $DISTRO $URL_NAME ${board_arch} $PLAT
        )
    done
done

set +e
##### Finish copying files to the lava-server machine #####

rm -fr jobs*
rm -fr results*

[ -d $GIT_DESCRIBE ] && rm -fr $GIT_DESCRIBE
mkdir -p $GIT_DESCRIBE/${RESULTS_DIR}

print_time "the time of preparing all envireonment is "

set -x

for DISTRO in $SHELL_DISTRO; 
do
	[ -d $DISTRO ] && rm -fr $DISTRO
    mkdir $DISTRO

   	rm -fr ${JOBS_DIR} ${RESULTS_DIR}
	# generate the boot jobs for all the targets
	if [ '$BOOT_PLAN'x != ''x ]; then
		generate_jobs $BOOT_PLAN $DISTRO
        [ $? -ne 0 ] && continue

		# create the boot jobs for each target and run all these jobs
        cd ${JOBS_DIR}
        ls
		python ../create_boot_job.py --username $LAVA_USER --token $LAVA_TOKEN --server $LAVA_SERVER --stream $LAVA_STREAM
		if [ $? -ne 0 ]; then
			echo "generate the jobs according the board devices error! Aborting"
			continue
		fi

		cd ..
        run_and_move_result $BOOT_PLAN $DISTRO
        [ $? -ne 0 ] && python parser.py -d $DISTRO && mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue
	fi 
	print_time "the end time of deploy $DISTRO in PXE is "
	#########################################
	##### Entering the sata disk rootfs #####
	# generate the boot jobs for all the target
    BOOT_FOR_TEST=BOOT_SAS
    rm -fr ${JOBS_DIR} ${RESULTS_DIR}
    generate_jobs $BOOT_FOR_TEST $DISTRO "--SasFlag"
    [ $? -ne 0 ] && continue
    cd ${JOBS_DIR}
	python ../create_boot_job.py --username $LAVA_USER --token $LAVA_TOKEN --server $LAVA_SERVER --stream $LAVA_STREAM
	if [ $? -ne 0 ]; then
		echo "generate the jobs according the board devices error! Aborting"
        cd .. && python parser.py -d $DISTRO && mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue 
	fi
	cd ..
	run_and_move_result $BOOT_FOR_TEST $DISTRO
    [ $? -ne 0 ] && python parser.py -d $DISTRO && mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue 
    print_time "the end time of boot $DISTRO fromhard disk is "
	##### End of entering the sata disk #####
	#########################################
	#####  modify the ip address according to the boot information
    DEVICE_IP='device_ip_type.txt'
    rm -fr /etc/lava-dispatcher/devices/$DEVICE_IP
    cat $DISTRO/${RESULTS_DIR}_${BOOT_FOR_TEST}/${LAVA_USER}/${DEVICE_IP}
    cp $DISTRO/${RESULTS_DIR}_${BOOT_FOR_TEST}/${LAVA_USER}/${DEVICE_IP} /etc/lava-dispatcher/devices
    cp modify_conf_file.sh /etc/lava-dispatcher/devices
    cd /etc/lava-dispatcher/devices; ./modify_conf_file.sh; cd -
    sudo rm -fr $HOME/.ssh/known_hosts
    if [ $? -ne 0 ]; then
    	echo "create ip and host mapping error! Aborting"
       	python parser.py  -d $DISTRO  &&  mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue 
    fi

	rm -fr ${JOBS_DIR} ${RESULTS_DIR}
	# generate the application jobs for the board_types 
	for app_plan in $APP_PLAN
	do
		[[ $app_plan =~ "BOOT" ]] && continue
    	generate_jobs $app_plan $DISTRO
        [ $? -ne 0 ] && python parser.py -d $DISTRO && mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue 
	done
	if [ -d ${JOBS_DIR} ]; then
        run_and_report_jobs
	    test -d ${RESULTS_DIR}  && mv ${RESULTS_DIR} ${RESULTS_DIR}_app
	    test -d ${JOBS_DIR}  && mv ${JOBS_DIR} ${JOBS_DIR}_app
        [ ! -d $DISTRO ]&& mkdir -p $DISTRO
        test -d ${JOBS_DIR}_app && mv ${JOBS_DIR}_app $DISTRO
	    test -d ${RESULTS_DIR}_app && mv ${RESULTS_DIR}_app $DISTRO
		[ $? -ne 0 ] && python parser.py -d $DISTRO && mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR} && continue 
	fi
    print_time "the end time of running app of $DISTRO is "
	python parser.py -d $DISTRO
    mv $DISTRO $GIT_DESCRIBE/${RESULTS_DIR}
done
##################################

DES_TMP=boot_results
[ -d $DES_TMP ] && rm -fr $DES_TMP
mkdir $DES_TMP

rm -fr ${JOBS_DIR} ${RESULTS_DIR}
# generate the boot jobs for the board_types 
for app_plan in $APP_PLAN
do
    [[ $app_plan =~ "BOOT" ]] && generate_jobs $app_plan
    [ ! -d ${JOBS_DIR} ] && continue
done

if [ -d ${JOBS_DIR} ]; then
	run_and_report_jobs 
	[ $? -ne 0 ] && exit -1
	test -d ${JOBS_DIR} && mv ${JOBS_DIR} $DES_TMP
	test -d ${RESULTS_DIR} && mv ${RESULTS_DIR} $DES_TMP
    python parser.py -d $DES_TMP
    mv $DES_TMP $GIT_DESCRIBE/${RESULTS_DIR}
    print_time "the end time of running boot tasks is "
fi 
##################################

# push the binary files to the ftpserver
#sudo python publish.py -j $TREE_NAME -d ./$GIT_DESCRIBE
DES_DIR=$FTP_DIR/$TREE_NAME/$GIT_DESCRIBE/
[ ! -d $DES_DIR ] && echo "Don't have the images and dtbs" && exit -1

pushd $GIT_DESCRIBE
python ../parser.py -s ${RESULTS_DIR}
popd

tar czf test_result.tar.gz $GIT_DESCRIBE/*
cp test_result.tar.gz  ${WORKSPACE}


WHOLE_SUM='whole_summary.txt'
if [  -e  ${WORKSPACE}/${WHOLE_SUM} ]; then
	rm -rf  ${WORKSPACE}/${WHOLE_SUM}
fi
cp $GIT_DESCRIBE/${RESULTS_DIR}/${WHOLE_SUM} ${WORKSPACE}
cp -rf $timefile ${WORKSPACE}


#zip -r ${GIT_DESCRIBE}_results.zip $GIT_DESCRIBE/*
cp -f $timefile $GIT_DESCRIBE

if [ -d $DES_DIR/$GIT_DESCRIBE/results ];then
	sudo rm -fr $DES_DIR/$GIT_DESCRIBE/results
    sudo rm -fr $DES_DIR/$GIT_DESCRIBE/$timefile
fi
sudo cp -rf $GIT_DESCRIBE/* $DES_DIR
[ $? -ne 0 ]&& exit -1

popd    # restore current work directory


cat ${WORKSPACE}/timestamp_boot.txt

if [ x"$BUILD_STATUS" != x"Successful"  ]; then
BUILD_RESULT=${BUILD_STATUS}
else
BUILD_RESULT=Failure
fi

