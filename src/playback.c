#include <alsa/asoundlib.h>
#include <mqueue.h>
#include <stdlib.h>
#include <stdio.h>
#include "common.h"


int main(int argc, char* argv[]) {
    mqd_t mq_output;
    sczr_shared_t* shm_output;
    FILE* log;

    set_sched();
    
    pcm_device_t device = {
        .name = PLAYBACK_DEVICE_NAME,
        .stream = SND_PCM_STREAM_PLAYBACK,
        .access = SND_PCM_ACCESS_RW_INTERLEAVED,
        .format = SND_PCM_FORMAT_S16_LE,
        .rate = Fs,
        .channels = PLAYBACK_CHANNELS,
        .buffer_time = BUFFER_TIME,
        .period_time = PERIOD_TIME
    };

    if(init_pcm_device(&device) < 0) {
        fprintf(stderr, "[playback] could not init playback device\n");
        return 1;
    }

    if(open_queue(MQ_OUTPUT, &mq_output) != 0) {
        snd_pcm_close(device.handle);
        fprintf(stderr, "[playback] could not open output queue\n");
        return 1;
    }

    if(wait_for_marker(mq_output) != 0) {
        mq_close(mq_output);
        snd_pcm_close(device.handle);
        fprintf(stderr, "[playback] marker timeout\n");
        return 1;
    }

    int input_period_size;
    mq_receive(mq_output, (char*)&input_period_size, MQ_MAX_MSG_SIZE, NULL);

    if(input_period_size != device.period_size) {
        mq_close(mq_output);
        snd_pcm_close(device.handle);
        fprintf(stderr, "[playback] input_period_size != output_period_size\n");
        return 1;
    }

    if(open_shared(SHM_OUTPUT, device.channels * device.period_size * sizeof(short), &shm_output) != 0) {
        snd_pcm_close(device.handle);
        mq_close(mq_output);
        fprintf(stderr, "[playback] could not init shared memory\n");
        return 1;
    }

    if((log = fopen(LOG_PLAYBACK, "w")) == NULL) {
        close_shared(shm_output);
        snd_pcm_close(device.handle);
        mq_close(mq_output);
        fprintf(stderr, "[playback] could not open log file\n");
        return 1;
    }

    printf("[playback] running\n");

    unsigned int buffer_index = 0;
    unsigned int block_id;
    int error;
    int periods = INT32_MAX;;

    if(argc > 1) {
        periods = atoi(argv[1]);
    }

    while(periods > 0) {
        mq_receive(mq_output, (char*) &buffer_index, MQ_MAX_MSG_SIZE, NULL);
        block_id = shm_output->buffers[buffer_index].block_id;
        int16_t* buffer_addr = (void*)shm_output + shm_output->buffers[buffer_index].offset;

        semaphore_wait(shm_output->semaphores_id, buffer_index);
        fprintf(log, "%d %lld\n", block_id, time_us());

        if((error = snd_pcm_writei(device.handle, buffer_addr, device.period_size)) < 0) {
            if(error == -EPIPE) {
                snd_pcm_prepare(device.handle);
            }
            else {
                printf("[playback] error: %s\n", snd_strerror(error));
            }
        }

        semaphore_signal(shm_output->semaphores_id, buffer_index);
        periods--;
    }

    destroy_shared(shm_output);
    mq_close(mq_output);
    snd_pcm_drain(device.handle);
    snd_pcm_close(device.handle);
    fclose(log);
    return 0;
}
