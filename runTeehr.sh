#!/bin/bash

_check_if_data_folder_exits(){
    # Check the directory exists
    if [ ! -d "$DATA_FOLDER_PATH" ]; then
        echo -e "${BRed}Directory does not exist. Exiting the program.${Color_Off}"
        exit 0
    fi
}

# Check if the config file exists and read from it
_check_and_read_config() {
    local config_file="$1"
    if [ -f "$config_file" ]; then
        local last_path=$(cat "$config_file")
        echo -e "Last used data directory path:\n" "$last_path${Color_Off}"
        read -erp "Do you want to use the same path? (Y/n): " use_last_path
        if [[ "$use_last_path" =~ ^[Yy] ]]; then
            DATA_FOLDER_PATH="$last_path"
            _check_if_data_folder_exits
            return 0
        elif [[ "$use_last_path" =~ ^[Nn] ]]; then
            read -erp "Enter your input data directory path (use absolute path): " DATA_FOLDER_PATH
            _check_if_data_folder_exits
            # Save the new path to the config file
            echo "$DATA_FOLDER_PATH" > "$CONFIG_FILE"
            echo -e "The Directory you've given is:\n$DATA_FOLDER_PATH\n${Color_Off}"
        else
            echo -e "Invalid input. Exiting.\n${Color_Off}" >&2
            return 1
        fi
    fi
}

check_last_path() {
    if [[ -z "$1" ]]; then
        _check_and_read_config "$CONFIG_FILE"

    else
        DATA_FOLDER_PATH="$1"
    fi
}

### Start of the Script ###

# Constants
CONFIG_FILE="$HOME/.host_data_path.conf"

check_last_path "$@"

IMAGE_NAME=awiciroh/ngiab-teehr

run_teehr_choice="Y"

# Execute the command
if [[ "$run_teehr_choice" == [Yy]* ]]; then

    # Get the TEEHR run options.
    choice () {
        local choice=$1
        if [[ ${run_opts[choice]} ]] # toggle
        then
            run_opts[choice]=
        else
            run_opts[choice]=+
        fi
    }
    PS3='Choose one or more options for the TEEHR evaluation, then choose Done: '
    while :
    do
        clear
        options=("Build the dataset ${run_opts[1]}" "Calculate Metrics ${run_opts[2]}" "Launch JupyterLab ${run_opts[3]}" "Done")
        select run_opt in "${options[@]}"
        do
            case $run_opt in
                "Build the dataset ${run_opts[1]}")
                    choice 1
                    break
                    ;;
                "Calculate Metrics ${run_opts[2]}")
                    choice 2
                    break
                    ;;
                "Launch JupyterLab ${run_opts[3]}")
                    choice 3
                    break
                    ;;
                "Done")
                    break 2
                    ;;
                *) printf '%s\n' 'invalid option';;
            esac
        done
    done
    run_opts_string=""
    for i in "${!run_opts[@]}"; do
        if [[ -n "${run_opts[$i]}" ]]; then
            run_opts_string+="$i,"
        fi
    done
    run_opts_string=${run_opts_string%,} # Comma-separated string

    # Get the image tag.
    echo -e "${UYellow}Specify the TEEHR image tag to use: ${Color_Off}"
    read -erp "Image tag (ex. v0.1.4, default: 'latest'): " teehr_image_tag
    if [[ -z "$teehr_image_tag" ]]; then
        if uname -a | grep arm64 || uname -a | grep aarch64 ; then
            teehr_image_tag=latest
        else
            teehr_image_tag=x86
        fi
    fi
    echo -e "${UYellow}Select an option (type a number): ${Color_Off}"
    options=("Run TEEHR using existing local docker image" "Run TEEHR after updating to latest docker image" "Exit")
    select option in "${options[@]}"; do
        case $option in
            "Run TEEHR using existing local docker image")
                break
                ;;
            "Run TEEHR after updating to latest docker image")
                echo "pulling container and running the TEEHR evaluation"
                docker pull $IMAGE_NAME:$teehr_image_tag
                break
                ;;
            Exit)
                echo "Have a nice day!"
                exit 0
                ;;
            *) echo "Invalid option $REPLY, 1 to continue with existing local image, 2 to update and run, and 3 to exit"
                ;;
        esac
    done

    if [[ ${run_opts[1]} || ${run_opts[2]} ]]; then
        if docker inspect -f '{{.State.Running}}' "teehr-evaluation" 2>/dev/null; then
            echo "The container is already running! Stopping it first..."
            docker container stop teehr-evaluation
            # Wait for the container to stop
            while docker inspect -f '{{.State.Running}}' "teehr-evaluation" 2>/dev/null | grep -q true; do
                sleep 10
            done
            sleep 2
            docker run --rm --name teehr-evaluation -e RUN_OPTIONS=$run_opts_string -v "$DATA_FOLDER_PATH:/app/data" "$IMAGE_NAME:$teehr_image_tag" run_teehr
        else
            # Run the TEEHR evaluation
            echo "The container is not running, starting a new one..."
            docker run --rm --name teehr-evaluation -e RUN_OPTIONS=$run_opts_string -v "$DATA_FOLDER_PATH:/app/data" "$IMAGE_NAME:$teehr_image_tag" run_teehr
        fi
        # Wait for the TEEHR evaluation to stop
        while docker inspect -f '{{.State.Running}}' "teehr-evaluation" 2>/dev/null | grep -q true; do
            sleep 1
        done
        echo -e "${GREEN}TEEHR evaluation complete.${RESET}\n"
    fi

    # Check if the run mode is 3 or 4
    if [[ ${run_opts[3]} ]]; then
        echo -e "${GREEN}Launching JupyterLab...${RESET}"
        docker run --rm --name teehr-evaluation -d -p 8888:8888 -v "$DATA_FOLDER_PATH:/app/data"  "$IMAGE_NAME:$teehr_image_tag" run_jupyter
        sleep 2
        firefox http://localhost:8888/lab/tree/01_Explore_NGIAB_output.ipynb
    fi

else
    echo -e "${CYAN}Skipping TEEHR evaluation step.${RESET}\n"
fi
