
# -*- coding: utf-8 -*-
"""
Created on Wed Jul 20 09:09:00 2022

@author: mustonel
"""

import numpy as np
from src import paths
import os
import json


def uncertainty(ff, droplets, z):
    """calculating the uncertainty of frozen fraction with method presented in Agresti and Coull 1998"""
    # n = number of droplets, z = confidence level (z=1.96 for 95 % confidence level)
    error_lower = []
    error_upper = []
    for f in ff:
        coeff = 1/(1+z**2/droplets)
        term1 = f
        term2 = z**2/(2*droplets)
        term3 = z * np.sqrt((f*(1-f))/droplets + (z**2)/(4*droplets**2))
        error_lower.append(coeff*(term1+term2-term3))
        error_upper.append(coeff*(term1+term2+term3))
    return np.array(error_lower), np.array(error_upper)



def bin_data(freezing_temps, bin_size, z):
    """bin freezing temp data to equal sized temperature intervals, calculate frozen fraction
    and add uncertainty"""
    freezing_temps = np.array(freezing_temps)[1::2] # take every other value (remove indices)
    droplets = len(freezing_temps) # number of droplets
    
    # temperature range and bin edges
    min_val = np.floor(freezing_temps.min() / bin_size) * bin_size
    max_val = np.ceil(freezing_temps.max() / bin_size) * bin_size
    bin_edges = np.arange(min_val, max_val + bin_size, bin_size)
    
    # Bin the values and count freezing events in the bin and calculate frozen fractions
    bin_counts, _ = np.histogram(freezing_temps, bins=bin_edges) # length of this array is 1 longer
    ff = np.cumsum(bin_counts[::-1]) / droplets # reverse the counts! (bin_edges are from cold to warm)
    ff = np.insert(ff, 0, 0) # add zero to the beginning of the array

    # calculate uncertainty limits and counts in each interval for differential spectrum calculations 
    lower_ff, upper_ff = uncertainty(ff, droplets, z)
    lower_counts = np.diff(np.round(droplets*lower_ff).astype(int))
    lower_counts = np.insert(lower_counts, 0, np.round(droplets*lower_ff).astype(int)[0])
    upper_counts = np.diff(np.round(droplets*upper_ff).astype(int))
    upper_counts = np.insert(upper_counts, 0, np.round(droplets*upper_ff).astype(int)[0])

    counts = np.diff(np.round(droplets * ff).astype(int))
    counts = np.insert(counts, 0, np.floor(droplets * ff).astype(int)[0])

    # temp is the upper temperature limit
    ff_data = np.zeros(len(bin_edges), dtype=[('temp', '<f8'), ('count', '<f8'),
                                                ('ff', '<f8'), ('count_lower_conf_lvl', '<f8'), 
                                                ('ff_lower_conf_lvl', '<f8'), ('count_upper_conf_lvl', '<f8'),
                                                ('ff_upper_conf_lvl', '<f8')])
    # create a numpy array of binned data
    ff_data['temp'] = np.insert(bin_edges[:-1][::-1], 0, max_val+bin_size) # if the frozen fraction does not align with raw, change the indexing to end
    ff_data['count'] = np.insert(bin_counts[::-1], 0, 0) 
    ff_data['ff'] = ff
    ff_data['count_lower_conf_lvl'] = lower_counts
    ff_data['ff_lower_conf_lvl'] = lower_ff
    ff_data['count_upper_conf_lvl'] = upper_counts
    ff_data['ff_upper_conf_lvl'] = upper_ff
    return ff_data


def differential(counts, bin_size, show_info=False):
    """calculate the differential spectrum of binned frozen fraction data and normalize"""
    # intialize spectrum
    droplets = np.sum(counts)
    n = droplets - np.insert(np.cumsum(counts), 0, 0)[:-1] # - np.cumsum(counts) # unfrozen droplets
    dn = counts # frozen droplets within each bin

    k = np.zeros(len(counts))
    epsilon = 2.2250738585072014*10**(-300) # normalized smallest available number 
    
    # calculate the rest in this loop, indicate abnormal behaviour with the prints
    for i in range(len(counts)):
        #dn = round(droplets * binned_ff[i]) - round(droplets * binned_ff[i - 1])
        #dn = counts[i]
        #n = droplets - np.sum(counts[i:])
        if dn[i] == 0.0:
            if show_info:
                print('no droplets froze in bin with index', i)
            k[i] = 0.0
        elif n[i] == 0.0:
            if show_info:
                print('no more unfrozen droplets at index', i)
            k[i] = 0.0 #- (1 / bin_size) * np.log(1 - (dn[i] / (n[i] + epsilon))) # Check if this is ok!!!
        elif dn[i]/n[i] == 1:
            k[i] = 0.0 
            if show_info:
                print('log goes to zero on index (dn/n=1)', i)
        elif 1 - (dn[i] / (n[i] + epsilon)) < 0.0:
            if show_info:
                print('dn > unfrozen droplets, something is wrong, check droplet count on index', i)
            k[i] = 0.0
        else:
            k[i] = - (1 / bin_size) * np.log(1 - (dn[i] / (n[i])))
    return k

def cumulative_from_diff(binned_k, bin_size):
    """calculate the cumulative spectrum from background corrected differential spectrum"""
    return np.cumsum(binned_k)*bin_size


def initialize_background(background_exp, bin_size, z):
    """ load background experiment data and analyze ready for background correction """
    freezing_temps = np.genfromtxt(os.path.join(paths.interim_data_path, background_exp, 'freezing_temps.csv'),
                             delimiter=',',
                             skip_header=1).flatten()
                             
    binned_bg = bin_data(freezing_temps, bin_size, z)
    diff = differential(binned_bg['count'], bin_size)
    diff_lower = differential(binned_bg['count_lower_conf_lvl'], bin_size)
    diff_upper = differential(binned_bg['count_upper_conf_lvl'], bin_size)

    # retrieve the background experiment normalisation factor
    with open(os.path.join(paths.raw_data_path, background_exp, 'metadata.json'), "r") as bgmetadata_file:
        bg_metadata = json.load(bgmetadata_file)
        normalisation_factor = float(bg_metadata.get("normalisation_factor", 1.0))  # Default to 1.0 if missing

    return binned_bg['temp'], binned_bg['ff'], binned_bg['ff_lower_conf_lvl'], binned_bg['ff_upper_conf_lvl'], \
        diff, diff_lower, diff_upper, normalisation_factor


def bg_correction(BG_temp, BG_ff, BG_diff, BG_lower, BG_upper, sample_temp, sample_ff, sample_diff,
                  sample_lower, sample_upper, show_info=False):
    """ calculate the background correction from binned differential data 
    function does not apply any normalisations"""
    corrected_diff = np.zeros(len(sample_temp))
    corrected_lower = np.zeros(len(sample_temp))
    corrected_upper = np.zeros(len(sample_temp))
    # changing the error format to perform addition of errors
    BG_lower = BG_diff - BG_lower
    BG_upper = BG_upper - BG_diff
    sample_lower = sample_diff - sample_lower
    sample_upper = sample_upper - sample_diff
    for i, t in enumerate(sample_temp):
        # berform correction, if sample temperature bin is in the background temperature bins
        if t in BG_temp:
            idx = np.where(np.isclose(BG_temp, t))[0][0]
            # if the difference is smaller than 0, set corrected value to zero
            if (sample_diff[i] - BG_diff[idx]) < 0:
                if show_info:
                    print(f'below zero value in bg correction at temperature {t}')
                corrected_diff[i], corrected_lower[i], corrected_upper[i] = 0, 0, 0
            # if frozen fraction of the sample has lower values than bg, set corrected value to zero
            elif sample_ff[i] < BG_ff[idx]:
                if show_info:
                    print(f'sample ff lower than background at temperature {t}!')
                corrected_diff[i], corrected_lower[i], corrected_upper[i] = 0, 0, 0
            # normal situation
            else:
                if show_info:
                    print(f'Background corrected at temp {t}')
                corrected_diff[i] = sample_diff[i] - BG_diff[idx]
                corrected_lower[i] = np.sqrt(sample_lower[i]**2 + BG_lower[idx]**2)
                corrected_upper[i] = np.sqrt(sample_upper[i]**2 + BG_upper[idx]**2)
        # if sample temperatures are lower than minimum background temperature result is 0
        elif t < np.min(BG_temp):
            if show_info:
                print(f'sample temp lower than minimum background at temperature {t}')
            corrected_diff[i], corrected_lower[i], corrected_upper[i] = 0, 0, 0
        # if sample temperature bin is not in the background temperature bins, differential is unchanged
        else:
            if show_info:
                print(f'no background correction needed at temperature {t}')
            corrected_diff[i], corrected_lower[i], corrected_upper[i] = sample_diff[i], sample_lower[i], sample_upper[i]

    # return  as confidence levels
    return corrected_diff, corrected_diff - corrected_lower, corrected_diff + corrected_upper


def spectra(freezing_temps, X, Y, bin_size, z, background_exp, depression=0):
    # X is normalisation factor before background
    # and Y normalisation after correction (generally Y is the sampled volume for filter experiments)
    """ calculate spectra to processed data with background correction
    note: all normalisation factors are handled in this function """
    droplets = len(freezing_temps)
    
    # bin data and calculate new error estimation to the binned frozen fraction data
    binned = bin_data(freezing_temps, bin_size, z)
    # calculate the differential and estimate errors by applying differential to limit of functions
    diff = differential(binned['count'], bin_size) * X
    diff_lower = differential(binned['count_lower_conf_lvl'], bin_size) * X
    diff_upper = differential(binned['count_upper_conf_lvl'], bin_size) * X

    
    # check if analyzed background experiment is available
    if background_exp != 'None' and background_exp is not None:
            bg_analysis = True
    else: bg_analysis = False

    if bg_analysis == False:
        # calculate cumulative spectrum from differential without bg correction
        # (these are normalised only to droplet volume already in previous step)
        # estimate errors by applying cumulative sum to confidence level spectra
        cum = cumulative_from_diff(diff, bin_size)
        cum_lower = cumulative_from_diff(diff_lower, bin_size)
        cum_upper = cumulative_from_diff(diff_upper, bin_size)
        
    else:
        # calculate background correction to differential spectrum, normalise background to droplet volume
        bg_temp, bg_ff, bg_ff_lower, bg_ff_upper, bg_diff, bg_diff_lower, bg_diff_upper, X_bg = \
            initialize_background(background_exp, bin_size, z)
        # within the input, normalise the bg differential to bg droplet volume
        diff, diff_lower, diff_upper = bg_correction(bg_temp, bg_ff, bg_diff * X_bg,
                                                     bg_diff_lower * X_bg, bg_diff_upper * X_bg,
                                                     binned['temp'], binned['ff'], diff,
                                                     diff_lower, diff_upper)

        # calculate cumulative spectrum from corrected differential spectrum
        cum = cumulative_from_diff(diff, bin_size)
        cum_lower = cumulative_from_diff(diff_lower, bin_size)
        cum_upper = cumulative_from_diff(diff_upper, bin_size)


    # Create array with the binned temperature and spectra values
    spectra_data = np.zeros(len(binned['temp']), dtype=[('temp', '<f8'), ('ff', '<f8'),
                                                        ('ff_lower_conf_lvl', '<f8'), ('ff_upper_conf_lvl', '<f8'),
                                                        ('k', '<f8'), ('k_lower_conf_lvl', '<f8'), 
                                                        ('k_upper_conf_lvl', '<f8'), ('K', '<f8'), 
                                                        ('K_lower_conf_lvl', '<f8'), ('K_upper_conf_lvl', '<f8')])

    spectra_data['temp'] = binned['temp'] - depression

    # print('norm, volume', X, Y)
    spectra_data['ff'] = binned['ff']
    spectra_data['ff_lower_conf_lvl'] = binned['ff_lower_conf_lvl']
    spectra_data['ff_upper_conf_lvl'] = binned['ff_upper_conf_lvl']

    spectra_data['k'] = diff * Y
    spectra_data['k_lower_conf_lvl'] = diff_lower * Y
    spectra_data['k_upper_conf_lvl'] = diff_upper * Y

    spectra_data['K'] = cum * Y
    spectra_data['K_lower_conf_lvl'] = cum_lower * Y
    spectra_data['K_upper_conf_lvl'] = cum_upper * Y
    
    # print('BG analysis completed', bg_analysis)

    return spectra_data, bg_analysis


