// Twin: the same word 8'h96 shifted out at the next prescale value (16'd2),
// each data bit lasting 16 clocks; the target requires prescale 16'd1.
module cov_P22_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        s_axis_tvalid
);

  localparam logic [15:0] PS     = 16'd2;
  localparam logic [4:0]  PERIOD = 5'd15;

  reg [7:0] shift;
  reg       active;
  reg       done;
  reg       ok;
  reg [4:0] cyc;

  always @(posedge clk) begin
    if (rst) begin
      shift  <= 8'h00;
      active <= 1'b0;
      done   <= 1'b0;
      ok     <= 1'b0;
      cyc    <= 5'd0;
    end else begin
      done <= 1'b0;
      if (prescale_reg == 19'd0) begin
        cyc <= 5'd0;
      end else if (cyc != 5'd31) begin
        cyc <= cyc + 5'd1;
      end
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
        active <= (prescale == PS);
        shift  <= 8'h00;
        ok     <= 1'b1;
      end else if (active && prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
        shift <= {txd, shift[7:1]};
        if (cyc != PERIOD) begin
          ok <= 1'b0;
        end
        if (bit_cnt == 4'd1) begin
          done   <= 1'b1;
          active <= 1'b0;
        end
      end
      if (prescale != PS) begin
        active <= 1'b0;
      end
    end
  end

  P22_twin_tx_prescale2_96: cover property (@(posedge clk) disable iff (rst)
    done && ok && shift == 8'h96 && txd && bit_cnt == 4'd0 && prescale == 16'd2);

endmodule

bind uart_tx cov_P22_twin u_cov_P22_twin (.*);
